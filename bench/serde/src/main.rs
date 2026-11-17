//! The serde_json comparator for tools/bench.py: serde_json's ordinary
//! `Value` DOM, run as `bench/main.nia` runs the Nia library and printing the
//! same report.

use serde_json::Value;
use std::hint::black_box;
use std::io::{self, Read};
use std::time::Instant;

fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(args.len(), 3);
    let mode = args[1].as_str();
    assert!(matches!(mode, "parse" | "write" | "roundtrip" | "read" | "load"));
    let iterations: usize = args[2].parse().unwrap();
    assert!(iterations > 0);
    let mut corpus = Vec::new();
    io::stdin().read_to_end(&mut corpus).unwrap();
    // `read` only reads the input; `load` also parses it once and keeps the
    // document, so the difference of their peak resident memory is what the
    // document costs.
    if mode == "read" {
        println!("iterations=0 nodes=0 input_bytes={} output_bytes=0 elapsed_ns=1", corpus.len());
        return;
    }
    if mode == "load" {
        let start = Instant::now();
        let value: Value = serde_json::from_slice(&corpus).unwrap();
        let elapsed = start.elapsed().as_nanos();
        println!(
            "iterations=1 nodes={} input_bytes={} output_bytes=0 elapsed_ns={elapsed}",
            count_nodes(&value),
            corpus.len()
        );
        black_box(value);
        return;
    }
    let initial: Value = serde_json::from_slice(&corpus).unwrap();
    let total_nodes = count_nodes(&initial) * iterations;
    // Text is written into memory, into one buffer reused by every
    // iteration, as the other harnesses write it.
    let mut text = Vec::with_capacity(corpus.len());
    let mut output_bytes = 0;
    // Only the measured loop is timed.
    let start = Instant::now();
    if mode == "write" {
        for _ in 0..iterations {
            text.clear();
            serde_json::to_writer(&mut text, black_box(&initial)).unwrap();
            output_bytes += text.len();
        }
    } else {
        drop(initial);
        for _ in 0..iterations {
            let value: Value = serde_json::from_slice(black_box(&corpus)).unwrap();
            if mode == "roundtrip" {
                text.clear();
                serde_json::to_writer(&mut text, black_box(&value)).unwrap();
                output_bytes += text.len();
            }
            black_box(value);
        }
    }
    let elapsed = start.elapsed().as_nanos();
    println!("iterations={iterations} nodes={total_nodes} input_bytes={} output_bytes={output_bytes} elapsed_ns={elapsed}", corpus.len());
}

// Every value of the document, counting object keys, as tools/bench.py does.
fn count_nodes(value: &Value) -> usize {
    match value {
        Value::Array(values) => 1 + values.iter().map(count_nodes).sum::<usize>(),
        Value::Object(values) => 1 + values.len() + values.values().map(count_nodes).sum::<usize>(),
        _ => 1,
    }
}

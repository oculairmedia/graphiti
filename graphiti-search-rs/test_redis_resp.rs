use redis::Value;

fn main() {
    // Simulating the structure FalkorDB returns
    let results: Vec<Vec<Value>> = vec![
        // Headers
        vec![Value::Data(b"n".to_vec())],
        // Data rows
        vec![
            vec![
                vec![
                    vec![Value::Data(b"id".to_vec()), Value::Int(2)],
                    vec![Value::Data(b"labels".to_vec()), vec![Value::Data(b"TestNode".to_vec())]],
                    vec![Value::Data(b"properties".to_vec()), vec![
                        vec![Value::Data(b"uuid".to_vec()), Value::Data(b"node-1".to_vec())],
                        vec![Value::Data(b"name".to_vec()), Value::Data(b"Node 1".to_vec())],
                    ]],
                ]
            ]
        ],
        // Stats
        vec![
            Value::Data(b"Cached execution: 0".to_vec()),
            Value::Data(b"Query internal execution time: 0.398888 milliseconds".to_vec()),
        ]
    ];
    
    println!("Results length: {}", results.len());
    println!("Data rows (index 1) length: {}", results[1].len());
    
    // Check what we actually have at results[1][0]
    if let Some(first_row) = results[1].get(0) {
        match first_row {
            Value::Bulk(cols) => {
                println!("First row is Bulk with {} columns", cols.len());
            }
            Value::Data(d) => {
                println!("First row is Data: {:?}", String::from_utf8_lossy(d));
            }
            Value::Int(i) => {
                println!("First row is Int: {}", i);
            }
            _ => {
                println!("First row is something else: {:?}", first_row);
            }
        }
    }
}
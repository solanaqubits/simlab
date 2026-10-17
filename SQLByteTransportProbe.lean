/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLByteIO
import Verification.NumericSQLByteTransport

/-! SQLByteTransportProbe — exact SQL verification support. -/
open Lean SQLByteIO NumericSQLByteTransport

def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let r ← readFrame input (2*1024*1024)
    if let .error e := r then
      if e != "eof" then
        output.putStrLn (Json.mkObj [("status", .str (if e == "resource_limit" then
          "resource_limit" else "invalid_input"))]).compress
      break
    let .ok bs := r | break
    let result := match decodeByteArray 21 bs with
      | .error e => Json.mkObj [("status", .str (if e == "resource_limit" then
          "resource_limit" else "invalid_input")), ("reason", .str e)]
      | .ok t => Json.mkObj [("status", .str "decoded"),
          ("tree", NumericSQLASTTransport.encode t)]
    output.putStrLn result.compress
    output.flush

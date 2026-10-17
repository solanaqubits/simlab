/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLASTTransport
import Lean.Data.Json.Parser

/-! Test-only IO wrapper. Its parser and JSON output are not part of the theorem. -/
open Lean NumericSQLASTTransport

def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let answer := if line.utf8ByteSize > 2 * 1024 * 1024 then
      Json.mkObj [("status", .str "resource_limit")]
    else match Json.parse line with
      | .error _ => Json.mkObj [("status", .str "invalid_input")]
      | .ok j => match fromTransport 21 j with
        | .error e => Json.mkObj [("status", .str (if e == "resource_limit" then
            "resource_limit" else "invalid_input"))]
        | .ok t => Json.mkObj [("status", .str "decoded"), ("tree", encode t)]
    output.putStrLn answer.compress
    output.flush

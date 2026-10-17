/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLDecoderRuntime

/-! SQLInstanceDecoderMain — exact SQL verification support. -/
open Lean SQLDecoderRuntime

def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let answer := if line.utf8ByteSize > 2 * 1024 * 1024 then
      refusal "resource_limit" "transport_bytes"
    else match Json.parse line with
      | .error _ => refusal "invalid_input" "transport_json"
      | .ok j => process j
    output.putStrLn answer.compress
    output.flush

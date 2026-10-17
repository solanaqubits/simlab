/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLByteIO
import SQLDecoderRuntime
import Verification.NumericSQLByteTransport

/-! IO framing and trusted context adapter remain outside the byte decoder theorem.
The request body is read as ByteArray and passed to decodeByteArray without JSON. -/
open Lean NumericSQLExpectedInstance SQLDecoderRuntime SQLByteIO

private def answer (context body : ByteArray) : Json := Id.run do
  let some contextText := String.fromUTF8? context |
    return refusal "invalid_context" "context_utf8"
  let .ok contextJson := Json.parse contextText |
    return refusal "invalid_context" "context_json"
  let .ok expected := readExpected contextJson |
    return refusal "invalid_context" "context_format"
  match NumericSQLByteTransport.decodeByteArray 21 body with
  | .error reason =>
    return refusal (if reason == "resource_limit" then "resource_limit" else "invalid_input")
      ("byte_transport:" ++ reason)
  | .ok tree => return processTree expected tree

def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let c ← readFrame input 16384
    if let .error e := c then
      if e != "eof" then
        output.putStrLn (refusal (if e == "resource_limit" then "resource_limit" else
          "invalid_context") "context_frame").compress
      break
    let b ← readFrame input (2*1024*1024)
    if let .error e := b then
      output.putStrLn (refusal (if e == "resource_limit" then "resource_limit" else "invalid_input")
        "body_frame").compress
      break
    let .ok context := c | break
    let .ok body := b | break
    output.putStrLn (answer context body).compress
    output.flush

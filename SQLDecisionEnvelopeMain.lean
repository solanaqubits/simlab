/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLByteIO
import SQLDecoderRuntime
import Verification.NumericSQLDecisionEnvelope

/-! Native binary response IO. No Python arithmetic or JSON response reconstruction.
Context provenance, control JSON parser, stream framing and compiled runtime remain external. -/
open Lean SQLByteIO SQLDecoderRuntime NumericSQLExpectedInstance NumericSQLDecisionEnvelope

private def contextValue (bs : ByteArray) : Option ExpectedInstance := do
  let s ← String.fromUTF8? bs
  let j ← (Json.parse s).toOption
  let id ← (j.getObjValAs? String "context_id").toOption
  if id.isEmpty || id.length > 128 then none else do
    let input ← (j.getObjVal? "input").toOption
    let e ← (readExpected input).toOption
    return {e with contextId := id}

private def frame (output : IO.FS.Stream) (bs : List UInt8) : IO Unit := do
  let n := bs.length
  let head := [UInt8.ofNat (n / 16777216),UInt8.ofNat (n / 65536),
    UInt8.ofNat (n / 256),UInt8.ofNat n]
  output.write ⟨(head ++ bs).toArray⟩
  output.flush

private def send (output : IO.FS.Stream) (r : Envelope) : IO Unit := do
  match emit r with
  | .ok bs => frame output bs
  | .error _ =>
    match emit ⟨"", .rejected .resourceLimit⟩ with
    | .ok bs => frame output bs
    | .error _ => throw (IO.userError "constant response encoding failed")

def main (args : List String) : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  let checking := args == ["--consume"]
  if !(args.isEmpty || checking) then return 2
  repeat
    let c ← readFrame input 16384
    if let .error e := c then
      if e != "eof" then send output ⟨"", .rejected .invalidContext⟩
      break
    let b ← readFrame input 262144
    if let .error e := b then
      send output ⟨"", .rejected (if e == "resource_limit" then .resourceLimit else .invalidInput)⟩
      break
    let .ok ctx := c | break
    let .ok raw := b | break
    let e := contextValue ctx
    if checking then
      let reply ← readFrame input (2*1024*1024)
      match reply with
      | .error _ => frame output [0]
      | .ok wire => frame output [if (consume e raw wire.data.toList).isSome then 1 else 0]
    else send output (run e raw)
  return 0

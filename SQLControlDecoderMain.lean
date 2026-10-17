/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLByteIO
import Verification.NumericSQLControlDecoder

/-! Native binary response IO. No Python arithmetic or JSON response reconstruction.
Control-byte semantics is checked in Lean. Provenance, framing and runtime remain external. -/
open SQLByteIO NumericSQLExpectedInstance NumericSQLDecisionEnvelope NumericSQLControlDecoder

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
      if e != "eof" then
        send output ⟨"", .rejected
          (if e == "resource_limit" then .resourceLimit else .invalidContext)⟩
      break
    let b ← readFrame input 262144
    if let .error e := b then
      send output ⟨"", .rejected (if e == "resource_limit" then .resourceLimit else .invalidInput)⟩
      break
    let .ok ctx := c | break
    let .ok raw := b | break
    if checking then
      let reply ← readFrame input (2*1024*1024)
      match reply with
      | .error _ => frame output [0]
      | .ok wire => frame output [if (consumeControl ctx raw wire.data.toList).isSome then 1 else 0]
    else send output (runControl ctx raw)
  return 0

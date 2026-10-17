/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import SQLByteIO
import Verification.NumericSQLSessionBinding

/-! Trusted startup file is separate from untrusted stdin. No per-request control.
IO delivery, pathname authorization and runtime are explicitly outside the proof. -/
open SQLByteIO NumericSQLDecisionEnvelope NumericSQLSessionBinding

private def frame (output : IO.FS.Stream) (bs : List UInt8) : IO Unit := do
  let n := bs.length
  output.write ⟨([UInt8.ofNat (n/16777216), UInt8.ofNat (n/65536),
    UInt8.ofNat (n/256), UInt8.ofNat n] ++ bs).toArray⟩
  output.flush

private def send (output : IO.FS.Stream) (r : Envelope) : IO Unit := do
  match emit r with
  | .ok bs => frame output bs
  | .error _ =>
    match emit ⟨"", .rejected .resourceLimit⟩ with
    | .ok bs => frame output bs
    | .error _ => throw (IO.userError "constant reply encoding failure")

/-- One handle, bounded reads; no pathname reread after startup. -/
private def readControl (h : IO.FS.Handle) : Nat → Nat → ByteArray → IO ByteArray
  | 0, _, acc => pure acc
  | fuel+1, remaining, acc => do
    if remaining == 0 then return acc
    let b ← h.read (min remaining 4096).toUSize
    if b.isEmpty then return acc
    readControl h fuel (remaining-b.size) (acc++b)

/-- IO assembles a bounded frame; the pure validator is called before dispatch. -/
private def receive (input : IO.FS.Stream) : IO (Except String (List UInt8 × ByteArray)) := do
  let first ← input.read 1
  if first.isEmpty then return .error "eof"
  let some rest ← readExact input 3 | return .error "truncated_frame"
  let header := (first++rest).data.toList
  if header.length != 4 then return .error "truncated_frame"
  let n := declaredLength header
  if n > 262144 then return .error "resource_limit"
  let some body ← readExact input n | return .error "truncated_frame"
  match checkFrame 262144 header body with
  | .error .resourceLimit => return .error "resource_limit"
  | .error _ => return .error "truncated_frame"
  | .ok _ => return .ok (header, body)

def main (args : List String) : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  let (path, budget, checking) ← match args with
    | ["--context", p, "--budget", n] => pure (p, n.toNat?, false)
    | ["--context", p, "--budget", n, "--consume"] => pure (p, n.toNat?, true)
    | _ => send output ⟨"", .rejected .invalidContext⟩; return 2
  let some limit := budget | send output ⟨"", .rejected .invalidContext⟩; return 2
  if limit > 1024 then send output ⟨"", .rejected .resourceLimit⟩; return 2
  let control ← try
    let h ← IO.FS.Handle.mk path .read
    pure (some (← readControl h 16386 16385 ByteArray.empty))
    catch _ => pure none
  let some bytes := control | send output ⟨"", .rejected .invalidContext⟩; return 2
  let initial ← match start bytes limit with
    | .error e =>
      send output ⟨"", .rejected
        (if e == "resource_limit" then .resourceLimit else .invalidContext)⟩
      return 2
    | .ok s => pure s
  -- Ready marker only. It carries no mathematical claim.
  frame output [1]
  let mut session := initial
  repeat
    let incoming ← receive input
    let (header, body) ← match incoming with
      | .error "eof" => break
      | .error e =>
        send output ⟨session.expected.contextId, .rejected
          (if e == "resource_limit" then .resourceLimit else .invalidInput)⟩
        break
      | .ok p => pure p
    let exhausted := session.remaining == 0
    if checking then
      let reply ← readFrame input (2*1024*1024)
      match reply with
      | .error _ => frame output [0]; break
      | .ok wire =>
        match consume session header body wire.data.toList with
        | none => frame output [0]; break
        | some (next, _) => session := next; frame output [1]
    else
      let (next, r) := dispatch session header body
      session := next
      send output r
    if exhausted then break
  return 0

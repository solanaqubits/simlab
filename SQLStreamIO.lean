/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLStreamReader

/-! Only the actual read effect remains here. Accumulation/EOF decisions use proved code. -/
namespace SQLStreamIO
open NumericSQLStreamReader NumericSQLSessionBinding NumericSQLDecisionEnvelope

def drive (input : IO.FS.Stream) (cleanEOF : Bool) : Nat → Machine → IO (Except ReadError Bytes)
  | _, .done bytes => pure (.ok bytes)
  | _, .failed why => pure (.error why)
  | 0, .active _ => pure (.error .resourceLimit)
  | fuel+1, m@(.active s) => do
    let raw ← input.read (min (remaining s) 4096).toUSize
    let event := if raw.isEmpty then Event.eof else .data raw.data.toList
    drive input cleanEOF fuel (advance cleanEOF m event)

def readExactly (input : IO.FS.Stream) (n : Nat) (cleanEOF : Bool) :
    IO (Except ReadError Bytes) := drive input cleanEOF (n+1) (initial n)

def reason : ReadError → String
  | .eof => "eof"
  | .truncated => "truncated_frame"
  | .invalidChunk => "invalid_chunk"
  | .resourceLimit => "resource_limit"

def readFrame (input : IO.FS.Stream) (cap : Nat) :
    IO (Except String (Bytes × ByteArray)) := do
  let hs ← readExactly input 4 true
  let header ← match hs with
    | .error why => return .error (reason why)
    | .ok h => pure h
  let n := declaredLength header
  if n > cap then return .error "resource_limit"
  let bs ← readExactly input n false
  let body ← match bs with
    | .error why => return .error (reason why)
    | .ok b => pure b
  match frameResult cap header body with
  | .error .resourceLimit => return .error "resource_limit"
  | .error _ => return .error "invalid_frame"
  | .ok p => return .ok p
end SQLStreamIO

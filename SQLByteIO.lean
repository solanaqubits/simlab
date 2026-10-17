/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Lean

/-! SQLByteIO — exact SQL verification support. -/
namespace SQLByteIO
def readLoop (input : IO.FS.Stream) : Nat → Nat → ByteArray → IO (Option ByteArray)
  | 0, _, _ => pure none
  | fuel+1, remaining, acc => do
    if remaining == 0 then return some acc
    let bs ← input.read remaining.toUSize
    if bs.isEmpty || bs.size > remaining then return none
    readLoop input fuel (remaining-bs.size) (acc ++ bs)

def readExact (input : IO.FS.Stream) (n : Nat) : IO (Option ByteArray) :=
  readLoop input (n+1) n ByteArray.empty

def readFrame (input : IO.FS.Stream) (cap : Nat) : IO (Except String ByteArray) := do
  let first ← input.read 1
  if first.isEmpty then return .error "eof"
  let some rest ← readExact input 3 | return .error "truncated_frame"
  let head := first ++ rest
  let n := head.data.toList.foldl (fun a b => 256*a+b.toNat) 0
  if n > cap then return .error "resource_limit"
  let some bs ← readExact input n | return .error "truncated_frame"
  return .ok bs


end SQLByteIO

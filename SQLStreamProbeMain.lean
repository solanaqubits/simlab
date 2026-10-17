/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLStreamReader
/-! Test-only decimal trace adapter. It is not the production byte parser. -/
open NumericSQLStreamReader

def bytesText (b : Bytes) : String := String.intercalate "," (b.map (toString ·.toNat))
def showState : Machine → String
  | .done b => "done:" ++ bytesText b
  | .active s => "active:" ++ toString s.target ++ ":" ++ bytesText s.bytes
  | .failed .eof => "failed:eof"
  | .failed .truncated => "failed:truncated"
  | .failed .invalidChunk => "failed:invalid_chunk"
  | .failed .resourceLimit => "failed:resource_limit"

def event (s : String) : Option Event := do
  if s == "E" then return .eof
  if s == "-" then return .data []
  let parts := s.splitOn ","
  if parts.length > 64 then none else do
  let ns ← parts.mapM String.toNat?
  if ns.any (· > 255) then none else return .data (ns.map UInt8.ofNat)

def query (line : String) : String := Id.run do
  if line.length > 8192 then return "adapter:resource_limit"
  let parts := line.trimAscii.toString.splitOn " "
  let n :: clean :: events := parts | return "adapter:invalid_input"
  let some target := n.toNat? | return "adapter:invalid_input"
  if target > 64 || events.length > 64 then return "adapter:resource_limit"
  if clean != "0" && clean != "1" then return "adapter:invalid_input"
  let some es := events.mapM event | return "adapter:invalid_input"
  return showState (replay (clean == "1") (initial target) es)

def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    output.putStrLn (query line)
    output.flush

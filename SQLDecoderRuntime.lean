/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLASTTransport
import Lean.Data.Json.Parser
import Lean.Data.Json.FromToJson.Basic

/-! JSON byte parsing/IO remain external. Tagged AST decoding uses the verified transport. -/
namespace SQLDecoderRuntime
open Lean NumericSQLInstanceDecoder NumericSQLExpectedInstance NumericSQLASTTransport


def obj (fields : List (String × Json)) : Json := Json.mkObj fields

def refusal (status reason : String) : Json := obj [
  ("status", toJson status), ("reason", toJson reason), ("decoder", toJson "1.0.2")]

def ratJson (q : ℚ) : Json := obj [
  ("numerator", toJson (toString q.num)), ("denominator", toJson (toString q.den))]

def instanceJson (x : SQLInstance) : Json := obj [
  ("A", ratJson x.A), ("B", ratJson x.B), ("I", ratJson x.I),
  ("semantics", toJson (match x.semantics with | .decimal => "decimal" | .binary64 => "binary64"))]

def readRat (j : Json) : Except String ℚ := do
  let n ← (← j.getObjVal? "numerator").getStr?
  let d ← (← j.getObjVal? "denominator").getStr?
  if n.length > 1300 || d.length > 1300 then throw "context_resource"
  let some ni := n.toInt? | throw "numerator"
  let some di := d.toNat? | throw "denominator"
  if di == 0 then throw "denominator"
  let q : ℚ := (ni : ℚ) / (di : ℚ)
  if !(decide (0 < q ∧ ratBudget q 4096)) then throw "context_domain"
  return q

def readExpected (j : Json) : Except String ExpectedInstance := do
  let sem ← (← j.getObjVal? "semantics").getStr?
  let mode ← if sem == "decimal" then pure InputSemantics.decimal else
    if sem == "binary64" then pure InputSemantics.binary64 else throw "context_semantics"
  let a ← readRat (← j.getObjVal? "A")
  let b ← readRat (← j.getObjVal? "B")
  let i ← readRat (← j.getObjVal? "I")
  return ⟨"separate-operator-argument", ⟨a, b, i, mode⟩⟩

def numberReason (sem : InputSemantics) (s : String) : Option (String × String) := Id.run do
  if s.length > 4096 then return some ("resource_limit", "parameter_length")
  let l := NumericSQLDecimalDecoder.lex s.toList
  if !(decide (l.Valid ∧ l.render = s.toList)) then
    return some ("invalid_input", "parameter_syntax")
  if !(decide (NumericSQLDecimalDecoder.withinLimits l)) then
    return some ("resource_limit", "decimal_exponent")
  let q := l.value
  if !(decide (ratBudget q 16384)) then return some ("resource_limit", "source_rational_bits")
  if !(decide (0 < q)) then return some ("invalid_input", "positive_domain")
  let some v := convert sem q | return some ("invalid_input", "binary64_zero_or_overflow")
  if !(decide (ratBudget v 4096)) then return some ("resource_limit", "input_rational_bits")
  return none

def processTree (expected : ExpectedInstance) (tree : Tree) : Json := Id.run do
  let some src := extract tree | return refusal "invalid_input" "ast_schema"
  for s in [src.A, src.B, src.I] do
    if let some (status, reason) := numberReason src.semantics s then return refusal status reason
  let some actual := decodeAST tree | return refusal "resource_limit" "numerator_bits"
  if actual != expected.input then
    return obj [("status", toJson "instance_mismatch"), ("actual", instanceJson actual),
      ("reason", toJson "expected_values"), ("decoder", toJson "1.0.2")]
  return obj [("status", toJson "decoded"), ("actual", instanceJson actual),
    ("reason", toJson "typed_equal"), ("decoder", toJson "1.0.2")]

def process (j : Json) : Json := Id.run do
  let .ok ej := j.getObjVal? "expected" | return refusal "invalid_context" "missing_context"
  let .ok expected := readExpected ej | return refusal "invalid_context" "context_format"
  let .ok tj := j.getObjVal? "tree" | return refusal "invalid_input" "missing_tree"
  let tr := fromTransport 21 tj
  if let .error reason := tr then
    return refusal (if reason == "resource_limit" then "resource_limit" else "invalid_input")
      "ast_transport"
  let .ok tree := tr | return refusal "invalid_input" "ast_transport"
  return processTree expected tree

end SQLDecoderRuntime

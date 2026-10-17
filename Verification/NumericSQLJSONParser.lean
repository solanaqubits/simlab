/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLJSONGrammar

/-! Speculative concrete-syntax parsing followed by mandatory independent grammar
and original-byte validation. No Lean.Json.parse or Python parser is trusted. -/
namespace NumericSQLJSONParser
open NumericSQLJSONGrammar NumericSQLInstanceDecoder NumericSQLExpectedInstance

def white (cs : Chars) : Chars × Chars := (cs.takeWhile space,cs.dropWhile space)

def readUnit (cs : Chars) : Except String (JUnit × Chars) := do
  let c::rest := cs | throw "unfinished_escape"
  if c == 'u' then
    if rest.length < 4 then throw "unicode_escape"
    let hi := rest.take 4
    if !(decide (Hex4 hi)) then throw "unicode_escape"
    let tail := rest.drop 4
    let v := hex hi
    if 0xD800 ≤ v && v ≤ 0xDBFF then
      let '\\'::'u'::tail := tail | throw "surrogate_pair"
      let lo := tail.take 4
      let u := JUnit.pair hi lo
      if !(decide u.Valid) then throw "surrogate_pair"
      return (u,tail.drop 4)
    else
      let u := JUnit.unicode hi
      if !(decide u.Valid) then throw "unicode_scalar"
      return (u,tail)
  else
    let u := JUnit.escaped c
    if !(decide u.Valid) then throw "escape"
    return (u,rest)

def readUnits : Nat → Chars → Except String (List JUnit × Chars)
  | 0, _ => .error "resource_limit"
  | n+1, cs => do
    let c::rest := cs | throw "unfinished_string"
    if c == '"' then return ([],rest)
    if c == '\\' then
      let (u,tail) ← readUnit rest
      let (us,tail) ← readUnits n tail
      return (u::us,tail)
    else
      if c.toNat < 32 then throw "control_character"
      let (us,tail) ← readUnits n rest
      return (.literal c::us,tail)

def readString (limit : Nat) (cs : Chars) : Except String (List JUnit × Chars) := do
  let '"'::rest := cs | throw "string_start"
  readUnits (limit+1) rest

/-- Member loops are structurally bounded independently of depth fuel. -/
def arrayItems (read : Chars → Except String (Syntax × Chars)) :
    Nat → Chars → Except String (List Syntax × Chars)
  | 0, _ => .error "resource_limit"
  | n+1, cs => do
    let (x,tail) ← read cs
    match tail with
    | ']'::rest => return ([x],rest)
    | ','::rest =>
      let (xs,rest) ← arrayItems read n rest
      return (x::xs,rest)
    | _ => throw "array_separator"

def objectItems (read : Chars → Except String (Syntax × Chars)) : Nat → Chars →
    Except String (List (Chars × List JUnit × Chars × Syntax) × Chars)
  | 0, _ => .error "resource_limit"
  | n+1, cs => do
    let (l,cs) := white cs
    let (key,cs) ← readString 128 cs
    let (r,cs) := white cs
    let ':'::cs := cs | throw "colon"
    let (value,tail) ← read cs
    let p := (l,key,r,value)
    match tail with
    | '}'::rest => return ([p],rest)
    | ','::rest =>
      let (ps,rest) ← objectItems read n rest
      return (p::ps,rest)
    | _ => throw "object_separator"

def atom (cs : Chars) : Except String (Syntax × Chars) := do
  if cs.take 4 == "null".toList then return (.null,cs.drop 4)
  if cs.take 4 == "true".toList then return (.bool true,cs.drop 4)
  if cs.take 5 == "false".toList then return (.bool false,cs.drop 5)
  let (neg,rest) := if cs.head? == some '-' then (['-'],cs.drop 1) else ([],cs)
  let ds := rest.takeWhile digit
  let token := neg ++ ds
  if token.length > 6 then throw "resource_limit"
  if !(decide (IntegerToken token)) then throw "integer_syntax"
  return (.number token,rest.dropWhile digit)

def parse : Nat → Chars → Except String (Syntax × Chars)
  | 0, _ => .error "resource_limit"
  | n+1, input => do
    let (left,cs) := white input
    let (s,rest) ← match cs with
      | '"'::_ => do
        let (us,tail) ← readString 4096 cs
        pure (.string us,tail)
      | '['::tail => do
        let (lead,tail) := white tail
        match tail with
        | ']'::rest => pure (.array lead [],rest)
        | _ => do
          let (xs,tail) ← arrayItems (parse n) 1024 tail
          pure (.array lead xs,tail)
      | '{'::tail => do
        let (lead,tail) := white tail
        match tail with
        | '}'::rest => pure (.object lead [],rest)
        | _ => do
          let (ps,tail) ← objectItems (parse n) 1024 tail
          pure (.object lead ps,tail)
      | _ => atom cs
    let (right,rest) := white rest
    return (.pad left s right,rest)

def nodes : Syntax → Nat
  | .array _ xs => 1 + (xs.map nodes).sum
  | .object _ fs => 1 + (fs.map fun p => nodes p.2.2.2).sum
  | .pad _ s _ => nodes s
  | _ => 1
termination_by s => sizeOf s
decreasing_by
  all_goals simp_wf
  · decreasing_trivial
  · have h := List.sizeOf_lt_of_mem ‹_ ∈ _›
    rcases p with ⟨l,u,r,s⟩
    simp_all only [Prod.mk.sizeOf_spec]
    omega
  · omega

/-- The same original bytes, never a Python-reencoded copy, reach certify. -/
def decode (bs : ByteArray) : Except String Tree :=
  if bs.size > 262144 then .error "resource_limit"
  else match String.fromUTF8? bs with
  | none => .error "utf8"
  | some input => match parse 21 input.toList with
    | .error e => .error e
    | .ok (s,rest) =>
      if !rest.isEmpty then .error "trailing"
      else if nodes s > 50000 then .error "resource_limit"
      else match certify 64 bs.data.toList s with
      | none => .error "grammar_or_representation"
      | some t => .ok t

theorem decode_sound (bs : ByteArray) (t : Tree) (h : decode bs = .ok t) :
    Represents 64 bs.data.toList t := by
  unfold decode at h
  split at h
  · contradiction
  · cases hi : String.fromUTF8? bs with
    | none => simp [hi] at h
    | some input =>
      simp only [hi] at h
      cases hp : parse 21 input.toList with
      | error err => simp [hp] at h
      | ok pair =>
        simp only [hp] at h
        split at h
        · contradiction
        · split at h
          · contradiction
          · cases hc : certify 64 bs.data.toList pair.1 with
            | none => simp [hc] at h
            | some actual =>
              simp only [hc, Except.ok.injEq] at h
              exact h ▸ certify_sound _ _ _ actual hc

def acceptJSON (e : ExpectedInstance) (bs : ByteArray) (p : ParsedBoundCertificate) : Bool :=
  match decode bs with
  | .error _ => false
  | .ok t => acceptDecoded e t p

theorem accepted_json_rounding (e : ExpectedInstance) (bs : ByteArray)
    (p : ParsedBoundCertificate) (h : acceptJSON e bs p = true) :
    ∃ t, Represents 64 bs.data.toList t ∧ ASTRep t e.input ∧
      decodeAST t = some e.input ∧
      NumericRealRounding.realRound NumericRoundingCertificates.binary64 e.input.gap
        = p.result := by
  unfold acceptJSON at h
  cases hd : decode bs with
  | error err => simp [hd] at h
  | ok t =>
    simp only [hd] at h
    have hr := accepted_decoded_rounding e t p h
    exact ⟨t,decode_sound bs t hd,decodeAST_sound t e.input hr.1,hr⟩

theorem different_instance_rejected (e : ExpectedInstance) (bs : ByteArray)
    (p : ParsedBoundCertificate) (t : Tree) (x : SQLInstance)
    (ht : decode bs = .ok t) (hx : decodeAST t = some x) (hne : x ≠ e.input) :
    acceptJSON e bs p = false := by
  simp only [acceptJSON, ht]
  exact decoded_mismatch_rejected e t p x hx hne

theorem decode_unique (bs : ByteArray) (t u : Tree)
    (ht : decode bs = .ok t) (hu : decode bs = .ok u) : t = u :=
  Except.ok.inj (ht.symm.trans hu)

/-- An infinite explicit completeness subset for the string lexer: raw scalar literals. -/
theorem literal_string_complete (fuel : Nat) (cs tail : Chars)
    (hl : cs.length < fuel) (hg : ∀ c ∈ cs, (JUnit.literal c).Valid) :
    readUnits fuel (cs ++ '"'::tail) = .ok (cs.map JUnit.literal,tail) := by
  induction fuel generalizing cs with
  | zero => omega
  | succ n ih =>
    cases cs with
    | nil => simp [readUnits, pure, Except.pure]
    | cons c cs =>
      have hc := hg c (by simp)
      have hh : ∀ d ∈ cs, (JUnit.literal d).Valid := by intro d hd; exact hg d (by simp [hd])
      have hlen : cs.length < n := by simp only [List.length_cons] at hl; omega
      simp only [JUnit.Valid] at hc
      simp [readUnits, hc.2.1, hc.2.2, Nat.not_lt.mpr hc.1, ih cs hlen hh,
        bind, Except.bind, pure, Except.pure]

def literalDocument (cs : Chars) : Syntax := .pad [] (.string (cs.map JUnit.literal)) []

theorem parse_literal_complete (cs : Chars) (hl : cs.length ≤ 4096)
    (hg : ∀ c ∈ cs, (JUnit.literal c).Valid) :
    parse 21 ('"'::(cs ++ ['"'])) = .ok (literalDocument cs,[]) := by
  have hr := literal_string_complete 4097 cs [] (by omega) hg
  simp [parse, white, space, readString, hr, literalDocument,
    bind, Except.bind, pure, Except.pure]

theorem literal_render (cs : Chars) : render (literalDocument cs) = '"'::(cs ++ ['"']) := by
  simp [literalDocument, render, stringRaw, JUnit.raw, List.flatMap_map]

theorem literal_good (cs : Chars) (hl : cs.length ≤ 4096)
    (hg : ∀ c ∈ cs, (JUnit.literal c).Valid) : Good 64 (literalDocument cs) := by
  simpa [literalDocument, Good, Spaces, GoodString, hl] using hg

/-- Concrete parser completeness on ALL bounded literal scalar strings, not a list
of sampled documents. Container completeness is deliberately not assumed here. -/
theorem decode_literal_complete (cs : Chars) (hl : cs.length ≤ 4096)
    (hg : ∀ c ∈ cs, (JUnit.literal c).Valid)
    (hb : (String.ofList ('"'::(cs ++ ['"']))).toUTF8.size ≤ 262144) :
    decode (String.ofList ('"'::(cs ++ ['"']))).toUTF8 =
      .ok (.string (String.ofList cs)) := by
  have hr := NumericSQLByteTransport.utf8_roundtrip
    (String.ofList ('"'::(cs ++ ['"'])))
  simp only [NumericSQLByteTransport.utf8, Array.toArray_toList] at hr
  have hc := certify_complete 64 (literalDocument cs) (literal_good cs hl hg)
  rw [literal_render] at hc
  change String.fromUTF8? (String.ofList ('"'::(cs ++ ['"']))).toUTF8 =
    some (String.ofList ('"'::(cs ++ ['"']))) at hr
  unfold decode
  rw [if_neg (Nat.not_lt.mpr hb), hr]
  simp only [String.toList_ofList]
  rw [parse_literal_complete cs hl hg]
  simp only [List.isEmpty_nil, Bool.not_true, Bool.false_eq_true, ↓reduceIte]
  have hn : nodes (literalDocument cs) = 1 := by simp [literalDocument,nodes]
  rw [hn]
  simp only [show ¬(1 > 50000) by omega, ↓reduceIte, hc]
  congr 1
  simp [literalDocument,denote,stringValue,Function.comp_def,JUnit.value]

structure NumericSQLJSONParserSuite : Prop where
  grammar : ∀ fuel s, check fuel s = true ↔ Good fuel s
  sound : ∀ bs t, decode bs = .ok t → Represents 64 bs.data.toList t
  rounding : ∀ e bs p, acceptJSON e bs p = true →
    ∃ t, Represents 64 bs.data.toList t ∧ ASTRep t e.input ∧ decodeAST t = some e.input ∧
      NumericRealRounding.realRound NumericRoundingCertificates.binary64 e.input.gap = p.result

theorem numeric_sql_json_parser_master_suite : NumericSQLJSONParserSuite := {
  grammar := check_iff
  sound := decode_sound
  rounding := accepted_json_rounding
}
end NumericSQLJSONParser

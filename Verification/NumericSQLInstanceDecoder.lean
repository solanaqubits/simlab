/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLDecimalDecoder
import Verification.NumericSQLBinaryDecoder

/-! NumericSQLInstanceDecoder — exact SQL verification support. -/

namespace NumericSQLInstanceDecoder
open NumericSQLExpectedInstance
open NumericRoundingCertificates

/-- Lossless AST boundary: pair lists retain duplicate object keys. -/
inductive Tree where
  | null
  | bool (value : Bool)
  | number (token : String)
  | string (value : String)
  | array (values : List Tree)
  | object (fields : List (String × Tree))
  deriving Repr, BEq

structure Source where
  A : String
  B : String
  I : String
  semantics : InputSemantics
  deriving DecidableEq

def bits (n : ℕ) : ℕ := if n = 0 then 0 else n.log2 + 1

def ratBudget (q : ℚ) (limit : ℕ) : Prop := bits q.num.natAbs ≤ limit ∧ bits q.den ≤ limit
instance (q : ℚ) (limit : ℕ) : Decidable (ratBudget q limit) := inferInstanceAs (Decidable (_ ∧ _))

def convert (s : InputSemantics) (q : ℚ) : Option ℚ :=
  match s with
  | .decimal => some q
  | .binary64 => NumericSQLBinaryDecoder.represented q

def SemanticsRep (s : InputSemantics) (q v : ℚ) : Prop :=
  match s with
  | .decimal => v = q
  | .binary64 => NumericSQLBinaryDecoder.Represents q v

theorem convert_sound (s : InputSemantics) (q v : ℚ) (h : convert s q = some v) :
    SemanticsRep s q v := by
  cases s with
  | decimal => exact (Option.some.inj h).symm
  | binary64 => exact NumericSQLBinaryDecoder.represented_sound q v h

theorem convert_complete (s : InputSemantics) (q v : ℚ) (h : SemanticsRep s q v) :
    convert s q = some v := by
  cases s with
  | decimal => exact congrArg some h.symm
  | binary64 => exact NumericSQLBinaryDecoder.represented_complete q v h

def decodeNumber (sem : InputSemantics) (s : String) : Option ℚ :=
  match NumericSQLDecimalDecoder.decode s.toList with
  | none => none
  | some q => if ¬ (0 < q ∧ ratBudget q 16384) then none else
    match convert sem q with
    | none => none
    | some v => if 0 < v ∧ ratBudget v 4096 then some v else none

def NumberRep (sem : InputSemantics) (s : String) (v : ℚ) : Prop :=
  ∃ q, NumericSQLDecimalDecoder.Represents s.toList q ∧ 0 < q ∧
    ratBudget q 16384 ∧ SemanticsRep sem q v ∧ 0 < v ∧ ratBudget v 4096

theorem decodeNumber_sound (sem : InputSemantics) (s : String) (v : ℚ)
    (h : decodeNumber sem s = some v) : NumberRep sem s v := by
  unfold decodeNumber at h
  cases hd : NumericSQLDecimalDecoder.decode s.toList with
  | none => simp [hd] at h
  | some q =>
    simp only [hd] at h
    split at h
    next => contradiction
    next hp =>
      have hp' : 0 < q ∧ ratBudget q 16384 := Classical.not_not.mp hp
      cases hc : convert sem q with
      | none => simp [hc] at h
      | some u =>
        simp only [hc] at h
        split at h
        next hu =>
          have he := Option.some.inj h
          subst u
          exact ⟨q, NumericSQLDecimalDecoder.decode_sound _ _ hd, hp'.1, hp'.2,
            convert_sound _ _ _ hc, hu.1, hu.2⟩
        next => contradiction

def sourceBudget (x : SQLInstance) : Prop :=
  ratBudget ((x.A - x.B * x.I * x.I) ^ 2) 12000
instance (x : SQLInstance) : Decidable (sourceBudget x) :=
  inferInstanceAs (Decidable (ratBudget _ _))

def decodeSource (s : Source) : Option SQLInstance :=
  match decodeNumber s.semantics s.A, decodeNumber s.semantics s.B,
    decodeNumber s.semantics s.I with
  | some A, some B, some I =>
    let x : SQLInstance := ⟨A, B, I, s.semantics⟩
    if sourceBudget x then some x else none
  | _, _, _ => none

def SourceRep (s : Source) (x : SQLInstance) : Prop :=
  x.semantics = s.semantics ∧ NumberRep s.semantics s.A x.A ∧
    NumberRep s.semantics s.B x.B ∧ NumberRep s.semantics s.I x.I ∧ sourceBudget x

theorem decodeSource_sound (s : Source) (x : SQLInstance) (h : decodeSource s = some x) :
    SourceRep s x := by
  unfold decodeSource at h
  cases ha : decodeNumber s.semantics s.A with
  | none => simp [ha] at h
  | some a =>
    cases hb : decodeNumber s.semantics s.B with
    | none => simp [ha, hb] at h
    | some b =>
      cases hi : decodeNumber s.semantics s.I with
      | none => simp [ha, hb, hi] at h
      | some i =>
        simp only [ha, hb, hi] at h
        split at h
        next hl =>
          cases Option.some.inj h
          exact ⟨rfl, decodeNumber_sound _ _ _ ha, decodeNumber_sound _ _ _ hb,
            decodeNumber_sound _ _ _ hi, hl⟩
        next => contradiction

theorem source_positive (s : Source) (x : SQLInstance) (h : SourceRep s x) : x.Positive := by
  exact ⟨h.2.1.choose_spec.2.2.2.2.1, h.2.2.1.choose_spec.2.2.2.2.1,
    h.2.2.2.1.choose_spec.2.2.2.2.1⟩

/-- Structured lookup refuses duplicates, including equal-valued duplicates. -/
def field (t : Tree) (name : String) : Option Tree :=
  match t with
  | .object fs => match fs.filter (fun p => p.1 == name) with
    | [(_, v)] => some v
    | _ => none
  | _ => none

def text (t : Tree) : Option String := match t with | .string s => some s | _ => none

def keys (t : Tree) (names : List String) : Bool := match t with
  | .object fs => decide ((fs.map Prod.fst).Nodup) &&
      decide (fs.length = names.length) && fs.all (fun p => names.contains p.1)
  | _ => false

def stringField (t : Tree) (name : String) : Option String := (field t name).bind text

def label (s : String) : Bool :=
  !s.isEmpty && s.length ≤ 128 && s.toList.all (fun c =>
    ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || ('0' ≤ c && c ≤ '9') ||
      ['_', '.', ':', '+', '-'].contains c)

def metadata (t : Tree) : Bool := Id.run do
  let some name := stringField t "request_id" | return false
  let some src := field t "source" | return false
  let some id := stringField src "case_id" | return false
  let some family := stringField src "family" | return false
  return label name && label id && family.length ≤ 128

def shape (t : Tree) (s : Source) : Prop :=
  metadata t = true ∧
  keys t ["schema", "request_id", "semantics", "expression", "format", "rounding",
    "zero_policy", "source", "certificate"] = true ∧
  stringField t "schema" = some "sql-expected-instance-request-1.0.0" ∧
  stringField t "expression" = some "sql-gap:A/I+B*I-2*sqrt(A*B);A>0,B>0,I>0" ∧
  stringField t "format" = some "binary64" ∧
  stringField t "rounding" = some "nearest-ties-to-even" ∧
  stringField t "zero_policy" = some "rational-exact-zero-is-positive" ∧
  stringField t "semantics" = some
    (match s.semantics with | .decimal => "decimal" | .binary64 => "binary64") ∧
  (match field t "source" with
   | some src => keys src ["case_id", "family", "strings"] = true ∧
     (match field src "strings" with
      | some ps => keys ps ["A", "B", "I", "hbar", "m", "omega_m"] = true ∧
        stringField ps "A" = some s.A ∧ stringField ps "B" = some s.B ∧
        stringField ps "I" = some s.I ∧
        (stringField ps "hbar").isSome = true ∧ (stringField ps "m").isSome = true ∧
        (stringField ps "omega_m").isSome = true
      | none => False)
   | none => False)
instance (t : Tree) (s : Source) : Decidable (shape t s) := by
  unfold shape
  repeat' first | infer_instance | split

/-- Candidate extraction followed by the explicit structural contract. -/
def extractCandidate (t : Tree) : Option Source := do
  let sem ← stringField t "semantics"
  let mode ← if sem = "decimal" then some InputSemantics.decimal else
    if sem = "binary64" then some InputSemantics.binary64 else none
  let src ← field t "source"
  let ps ← field src "strings"
  let A ← stringField ps "A"
  let B ← stringField ps "B"
  let I ← stringField ps "I"
  let s : Source := ⟨A, B, I, mode⟩
  return s

def extract (t : Tree) : Option Source :=
  match extractCandidate t with
  | none => none
  | some s => if shape t s then some s else none

def decodeAST (t : Tree) : Option SQLInstance := (extract t).bind decodeSource

theorem extract_sound (t : Tree) (s : Source) (h : extract t = some s) : shape t s := by
  unfold extract at h
  split at h
  next => contradiction
  next v hv =>
    split at h
    next hs => cases Option.some.inj h; exact hs
    next => contradiction

def ASTRep (t : Tree) (x : SQLInstance) : Prop := ∃ s, shape t s ∧ SourceRep s x

theorem decodeAST_sound (t : Tree) (x : SQLInstance) (h : decodeAST t = some x) :
    ASTRep t x := by
  unfold decodeAST at h
  cases he : extract t with
  | none => simp [he] at h
  | some s =>
    simp only [he, Option.bind_some] at h
    exact ⟨s, extract_sound _ _ he, decodeSource_sound _ _ h⟩

/-- Completeness of candidate extraction for the explicit field contract. -/
theorem extract_complete (t : Tree) (s : Source) (h : shape t s) : extract t = some s := by
  have hh := h
  unfold shape at h
  obtain ⟨_, _, _, _, _, _, _, hsem, hs⟩ := h
  cases hsrc : field t "source" with
  | none => simp [hsrc] at hs
  | some src =>
    simp only [hsrc] at hs
    cases hps : field src "strings" with
    | none => simp [hps] at hs
    | some ps =>
      simp only [hps] at hs
      obtain ⟨_, _, hA, hB, hI, _⟩ := hs
      have hc : extractCandidate t = some s := by
        cases s with
        | mk A B I sem =>
          cases sem <;> simp_all [extractCandidate]
      simp [extract, hc, hh]

def CanonicalNumber (sem : InputSemantics) (s : String) (v : ℚ) : Prop :=
  s.toList.all NumericSQLDecimalDecoder.digit = true ∧ s.toList ≠ [] ∧
  s.toList.length ≤ 4096 ∧
  (let q : ℚ := NumericSQLDecimalDecoder.positional s.toList
   0 < q ∧ ratBudget q 16384 ∧ SemanticsRep sem q v ∧ 0 < v ∧ ratBudget v 4096)

theorem canonical_number_complete (sem : InputSemantics) (s : String) (v : ℚ)
    (h : CanonicalNumber sem s v) : decodeNumber sem s = some v := by
  obtain ⟨hd, hn, hl, hp, hb, hs, hv, hbudget⟩ := h
  have he := NumericSQLDecimalDecoder.decode_integer_complete s.toList hd hn hl
  simp [decodeNumber, he, hp, hb, convert_complete _ _ _ hs, hv, hbudget]

def CanonicalSource (s : Source) (x : SQLInstance) : Prop :=
  x.semantics = s.semantics ∧ CanonicalNumber s.semantics s.A x.A ∧
    CanonicalNumber s.semantics s.B x.B ∧ CanonicalNumber s.semantics s.I x.I ∧ sourceBudget x

theorem canonical_source_complete (s : Source) (x : SQLInstance) (h : CanonicalSource s x) :
    decodeSource s = some x := by
  obtain ⟨hm, ha, hb, hi, hx⟩ := h
  have hA := canonical_number_complete _ _ _ ha
  have hB := canonical_number_complete _ _ _ hb
  have hI := canonical_number_complete _ _ _ hi
  have he : (⟨x.A, x.B, x.I, s.semantics⟩ : SQLInstance) = x := by cases x; simp_all
  simp [decodeSource, hA, hB, hI, he, hx]

theorem canonical_AST_complete (t : Tree) (s : Source) (x : SQLInstance)
    (hs : shape t s) (hx : CanonicalSource s x) : decodeAST t = some x := by
  simp [decodeAST, extract_complete _ _ hs, canonical_source_complete _ _ hx]


/-- Certificate actuals must be the decoded values, not another freely supplied copy. -/
def acceptDecoded (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate) : Bool :=
  match decodeAST t with
  | none => false
  | some x => decide (x = p.actual) && accept e p

theorem accepted_decoded_rounding (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : acceptDecoded e t p = true) :
    decodeAST t = some e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = p.result := by
  unfold acceptDecoded at h
  cases hd : decodeAST t with
  | none => simp [hd] at h
  | some x =>
    simp only [hd, Bool.and_eq_true, decide_eq_true_eq] at h
    have he := accepted_instance_eq e p h.2
    exact ⟨congrArg some (h.1.trans he), accepted_expected_rounding e p h.2⟩

theorem decoded_mismatch_rejected (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (x : SQLInstance) (hd : decodeAST t = some x) (hne : x ≠ e.input) :
    acceptDecoded e t p = false := by
  cases ha : acceptDecoded e t p with
  | false => rfl
  | true =>
    have he := (accepted_decoded_rounding e t p ha).1
    exact False.elim (hne (Option.some.inj (hd.symm.trans he)))

theorem decodeAST_unique (t : Tree) (x y : SQLInstance)
    (hx : decodeAST t = some x) (hy : decodeAST t = some y) : x = y :=
  Option.some.inj (hx.symm.trans hy)

structure NumericSQLInstanceDecoderSuite : Prop where
  decimal_sound : ∀ cs q, NumericSQLDecimalDecoder.decode cs = some q →
    NumericSQLDecimalDecoder.Represents cs q
  binary_sound : ∀ q v, NumericSQLBinaryDecoder.represented q = some v →
    NumericSQLBinaryDecoder.Represents q v
  ast_sound : ∀ t x, decodeAST t = some x → ASTRep t x
  rounding : ∀ e t p, acceptDecoded e t p = true →
    decodeAST t = some e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = p.result

theorem numeric_sql_instance_decoder_master_suite : NumericSQLInstanceDecoderSuite := {
  decimal_sound := NumericSQLDecimalDecoder.decode_sound
  binary_sound := NumericSQLBinaryDecoder.represented_sound
  ast_sound := decodeAST_sound
  rounding := accepted_decoded_rounding
}

end NumericSQLInstanceDecoder

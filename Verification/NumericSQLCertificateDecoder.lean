/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLJSONParser

/-! Version 1.0.1: certificate fields are read from the same original request Tree.
The declarative representation is checked after candidate extraction. Real soundness
uses the existing affine and full-cell kernel, not Python annotations or hashes. -/
namespace NumericSQLCertificateDecoder
open NumericSQLInstanceDecoder NumericSQLExpectedInstance NumericRoundingCertificates
open NumericSQLIntervalBounds NumericSQLJSONGrammar

/-- Paths use duplicate-refusing field lookup; no default values or coercions. -/
def atPath (t : Tree) : List String → Option Tree
  | [] => some t
  | k :: ks => (field t k).bind (fun u => atPath u ks)

def strAt (t : Tree) (ks : List String) : Option String := (atPath t ks).bind text

def RatRep (t : Tree) (q : ℚ) : Prop :=
  keys t ["numerator", "denominator"] = true ∧
  stringField t "numerator" = some (toString q.num) ∧
  stringField t "denominator" = some (toString q.den) ∧
  (toString q.num).length ≤ 3700 ∧ (toString q.den).length ≤ 3700 ∧ ratBudget q 12000
instance (t : Tree) (q : ℚ) : Decidable (RatRep t q) :=
  inferInstanceAs (Decidable (_ ∧ _ ∧ _ ∧ _ ∧ _ ∧ _))

def RatAt (t : Tree) (ks : List String) (q : ℚ) : Prop :=
  match atPath t ks with | none => False | some u => RatRep u q
instance (t : Tree) (ks : List String) (q : ℚ) : Decidable (RatAt t ks q) := by
  unfold RatAt; split <;> infer_instance

def hexChars : List Char := "0123456789abcdef".toList

def hexFixed : Nat → Nat → List Char
  | 0, _ => []
  | k+1, n => hexFixed k (n / 16) ++ [hexChars[n % 16]!]

def resultBits (f : FloatRepresentation binary64) : String :=
  String.ofList (hexFixed 16 ((if f.negative then 2^63 else 0) + f.magnitude.val))

/-- Representation conditions say which source fields have which exact meanings.
No condition here calls the candidate decoder or assumes rounding correctness. -/
def CertificateRep (t : Tree) (p : ParsedBoundCertificate) : Prop :=
  strAt t ["certificate", "schema"] = some "sql-direct-root-enclosure-1.0.0" ∧
  strAt t ["certificate", "method"] = some "direct_product_root" ∧
  strAt t ["certificate", "semantics"] = some
    (match p.actual.semantics with | .decimal => "decimal" | .binary64 => "binary64") ∧
  RatAt t ["certificate", "inputs", "A"] p.actual.A ∧
  RatAt t ["certificate", "inputs", "B"] p.actual.B ∧
  RatAt t ["certificate", "inputs", "I"] p.actual.I ∧
  RatAt t ["certificate", "root_lower"] p.root.lo ∧
  RatAt t ["certificate", "root_upper"] p.root.hi ∧
  strAt t ["certificate", "decision", "schema"] = some "rounding-decision-1.0.0" ∧
  strAt t ["certificate", "decision", "format"] = some "binary64" ∧
  strAt t ["certificate", "decision", "rounding"] = some "nearest-ties-to-even" ∧
  strAt t ["certificate", "decision", "zero_policy"] = some "rational-exact-zero-is-positive" ∧
  (strAt t ["certificate", "decision", "kind"] = some "interval" ∨
   strAt t ["certificate", "decision", "kind"] = some "exact_midpoint") ∧
  strAt t ["certificate", "decision", "result_bits"] = some (resultBits p.result)
instance (t : Tree) (p : ParsedBoundCertificate) : Decidable (CertificateRep t p) := by
  unfold CertificateRep; infer_instance

/-- Total digit fold; canonical spelling is independently checked by RatRep. -/
def unsigned (s : String) : Option Nat :=
  if s.isEmpty || !(s.toList.all NumericSQLDecimalDecoder.digit) then none
  else some (s.toList.foldl (fun n c => n * 10 + (c.toNat - '0'.toNat)) 0)

def signed (s : String) : Option Int :=
  match s.toList with
  | '-' :: cs => (unsigned (String.ofList cs)).map (fun n => -(n : Int))
  | _ => (unsigned s).map Int.ofNat

/-- At most 3700 characters are parsed; integer budget is checked before division. -/
def ratCandidate (t : Tree) : Except String ℚ := do
  let some ns := stringField t "numerator" | throw "rational_shape"
  let some ds := stringField t "denominator" | throw "rational_shape"
  if ns.length > 3700 || ds.length > 3700 then throw "resource_limit"
  let some n := signed ns | throw "rational_integer"
  let some d := unsigned ds | throw "rational_denominator"
  if d = 0 then throw "rational_denominator"
  if bits n.natAbs > 12000 || bits d > 12000 then throw "resource_limit"
  let q : ℚ := (n : ℚ) / (d : ℚ)
  return q

def readRat (t : Tree) : Except String ℚ := do
  let q ← ratCandidate t
  if RatRep t q then return q else throw "rational_representation"

theorem readRat_sound (t : Tree) (q : ℚ) (h : readRat t = .ok q) : RatRep t q := by
  unfold readRat at h
  cases hc : ratCandidate t with
  | error e => simp [hc,bind,Except.bind] at h
  | ok v =>
    simp only [hc,bind,Except.bind] at h
    split at h
    next hv => exact (Except.ok.inj h) ▸ hv
    next => contradiction

def ratAt (t : Tree) (ks : List String) : Except String ℚ := do
  let some u := atPath t ks | throw "missing_rational"
  readRat u

def readResult (s : String) : Except String (FloatRepresentation binary64) := do
  if s.length != 16 || !(s.toList.all (fun c => hexChars.contains c)) then throw "result_encoding"
  let raw := s.toList.foldl (fun n c => n * 16 + hexValue c) 0
  let mag := raw % 2^63
  if h : mag < binary64.last + 1 then
    let f : FloatRepresentation binary64 := ⟨decide (2^63 ≤ raw), ⟨mag,h⟩⟩
    if s = resultBits f then return f else throw "result_encoding"
  else throw "nan_encoding"

/-- Extraction is untrusted until the independent CertificateRep check below. -/
def candidate (t : Tree) : Except String ParsedBoundCertificate := do
  let some sem := strAt t ["certificate","semantics"] | throw "semantics"
  let mode ← if sem = "decimal" then pure InputSemantics.decimal else
    if sem = "binary64" then pure InputSemantics.binary64 else throw "semantics"
  let a ← ratAt t ["certificate","inputs","A"]
  let b ← ratAt t ["certificate","inputs","B"]
  let i ← ratAt t ["certificate","inputs","I"]
  let lo ← ratAt t ["certificate","root_lower"]
  let hi ← ratAt t ["certificate","root_upper"]
  if h : lo ≤ hi then
    let some kind := strAt t ["certificate","decision","kind"] | throw "decision_kind"
    if kind = "indeterminate" then throw "indeterminate"
    let some s := strAt t ["certificate","decision","result_bits"] | throw "result_encoding"
    let f ← readResult s
    return ⟨⟨a,b,i,mode⟩, ⟨lo,hi,h⟩, f⟩
  else throw "root_order"

def certify (t : Tree) (p : ParsedBoundCertificate) :
    Option {q : ParsedBoundCertificate // CertificateRep t q} :=
  if h : CertificateRep t p then some ⟨p,h⟩ else none

theorem certify_complete (t : Tree) (p : ParsedBoundCertificate) (h : CertificateRep t p) :
    ∃ q, certify t p = some q ∧ q.val = p := by
  exact ⟨⟨p,h⟩, by simp [certify,h], rfl⟩

def decodeCertificate (t : Tree) :
    Except String {p : ParsedBoundCertificate // CertificateRep t p} := do
  let p ← candidate t
  let some q := certify t p | throw "certificate_representation"
  return q

/-- The final real checker has no certificate argument supplied by Python. -/
def validateTree (e : ExpectedInstance) (t : Tree) : Except String ParsedBoundCertificate := do
  let some x := decodeAST t | throw "input_decode"
  if x != e.input then throw "instance_mismatch"
  let p ← decodeCertificate t
  if acceptDecoded e t p.val then return p.val else throw "mathematical_checks"

theorem validateTree_sound (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : validateTree e t = .ok p) : CertificateRep t p ∧
      decodeAST t = some e.input ∧
      NumericRealRounding.realRound binary64 e.input.gap = p.result := by
  unfold validateTree at h
  cases hx : decodeAST t with
  | none => simp [hx] at h
  | some x =>
    simp only [hx] at h
    split at h
    · simp_all [bind, Except.bind, throw]
    · cases hc : decodeCertificate t with
      | error err => simp [hc, bind, Except.bind] at h
      | ok q =>
        simp only [hc, bind, Except.bind] at h
        split at h
        next ha =>
          have he : q.val = p := Except.ok.inj h
          subst p
          exact ⟨q.property, by simpa [hx] using accepted_decoded_rounding e t q.val ha⟩
        next => simp_all

def validate (e : ExpectedInstance) (bs : ByteArray) : Except String ParsedBoundCertificate := do
  let t ← NumericSQLJSONParser.decode bs
  validateTree e t

theorem validated_original_bytes (e : ExpectedInstance) (bs : ByteArray)
    (p : ParsedBoundCertificate) (h : validate e bs = .ok p) :
    ∃ t, Represents 64 bs.data.toList t ∧ CertificateRep t p ∧
      ASTRep t e.input ∧ decodeAST t = some e.input ∧
      NumericRealRounding.realRound binary64 e.input.gap = p.result := by
  unfold validate at h
  cases ht : NumericSQLJSONParser.decode bs with
  | error err => simp [ht, bind, Except.bind] at h
  | ok t =>
    simp only [ht, bind, Except.bind] at h
    obtain ⟨hp,hx,hr⟩ := validateTree_sound e t p h
    exact ⟨t,NumericSQLJSONParser.decode_sound bs t ht,hp,decodeAST_sound t e.input hx,hx,hr⟩

/-- Every meaningful parameter in the accepted certificate is the expected one. -/
theorem validated_actual_eq (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : validateTree e t = .ok p) : p.actual = e.input := by
  unfold validateTree at h
  cases hx : decodeAST t with
  | none => simp [hx] at h
  | some x =>
    simp only [hx] at h
    split at h
    · simp_all [bind, Except.bind, throw]
    · cases hc : decodeCertificate t with
      | error err => simp [hc,bind,Except.bind] at h
      | ok q =>
        simp only [hc,bind,Except.bind] at h
        split at h
        next ha =>
          have he : q.val = p := Except.ok.inj h
          subst p
          unfold acceptDecoded at ha
          simp only [hx] at ha
          simp only [Bool.and_eq_true, decide_eq_true_eq] at ha
          exact accepted_instance_eq e q.val ha.2
        next => simp_all

/-- A different source instance cannot succeed, irrespective of result bits. -/
theorem other_source_rejected (e : ExpectedInstance) (t : Tree) (x : SQLInstance)
    (hx : decodeAST t = some x) (hne : x ≠ e.input) (p : ParsedBoundCertificate) :
    validateTree e t ≠ .ok p := by
  intro h
  have he := (validateTree_sound e t p h).2.1
  exact hne (Option.some.inj (hx.symm.trans he))

/-- Direct field transfer, not merely equality of hashes or of rounded results. -/
theorem validated_parameters (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : validateTree e t = .ok p) :
    RatAt t ["certificate","inputs","A"] e.input.A ∧
    RatAt t ["certificate","inputs","B"] e.input.B ∧
    RatAt t ["certificate","inputs","I"] e.input.I := by
  have hr := (validateTree_sound e t p h).1
  have he := validated_actual_eq e t p h
  unfold CertificateRep at hr
  exact he ▸ ⟨hr.2.2.2.1,hr.2.2.2.2.1,hr.2.2.2.2.2.1⟩

/-- The returned representation itself is the one encoded in the request. -/
theorem validated_result_field (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : validateTree e t = .ok p) :
    strAt t ["certificate","decision","result_bits"] = some (resultBits p.result) := by
  have hr := (validateTree_sound e t p h).1
  exact hr.2.2.2.2.2.2.2.2.2.2.2.2.2

structure NumericSQLCertificateDecoderSuite : Prop where
  representation : ∀ e t p, validateTree e t = .ok p → CertificateRep t p
  binding : ∀ e t p, validateTree e t = .ok p → p.actual = e.input
  rounding : ∀ e t p, validateTree e t = .ok p →
    NumericRealRounding.realRound binary64 e.input.gap = p.result

theorem numeric_sql_certificate_decoder_master_suite : NumericSQLCertificateDecoderSuite := {
  representation := fun e t p h => (validateTree_sound e t p h).1
  binding := validated_actual_eq
  rounding := fun e t p h => (validateTree_sound e t p h).2.2
}
end NumericSQLCertificateDecoder

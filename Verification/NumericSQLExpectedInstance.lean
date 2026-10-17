/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLGapBounds
import Verification.NumericCertificateDigestBridge

/-!
# SQL rounding bound to an externally selected instance

Version 1: the expression, binary64 grid, nearest-even rule and canonical zero
are fixed by this module. Input semantics is a tag for already decoded rationals,
not an implementation of decimal/JSON parsing. The caller supplies the expected
instance separately; neither a request ID nor a digest chooses it.
-/
namespace NumericSQLExpectedInstance

open NumericRoundingCertificates NumericRealRounding NumericSQLIntervalBounds
open NumericSQLGapBounds NumericCertificateDigestBridge

inductive InputSemantics where
  | decimal
  | binary64
  deriving DecidableEq, Repr

/-- Complete mathematical input in this fixed version/statement/format context. -/
structure SQLInstance where
  A : ℚ
  B : ℚ
  I : ℚ
  semantics : InputSemantics
  deriving DecidableEq

def SQLInstance.Positive (x : SQLInstance) : Prop := 0 < x.A ∧ 0 < x.B ∧ 0 < x.I
instance (x : SQLInstance) : Decidable x.Positive := inferInstanceAs (Decidable (_ ∧ _ ∧ _))

noncomputable def SQLInstance.gap (x : SQLInstance) : ℝ :=
  sqlNoiseGap (x.A : ℝ) (x.B : ℝ) (x.I : ℝ)

/-- Immutable caller-owned selection; contextId is for correlation, not lookup. -/
structure ExpectedInstance where
  contextId : String
  input : SQLInstance

/-- These inputs actually determine the product and affine endpoints checked below. -/
structure ParsedBoundCertificate where
  actual : SQLInstance
  root : RatInterval
  result : FloatRepresentation binary64

/-- No supplied enclosure endpoints can detach the certificate from its actual inputs. -/
def MathematicalChecks (p : ParsedBoundCertificate) : Prop :=
  checkSqrtWitness (productInterval p.actual.A p.actual.B) p.root = true ∧
  checkIntervalCertificate binary64
    (gapInterval p.actual.A p.actual.B p.actual.I p.root).lo
    (gapInterval p.actual.A p.actual.B p.actual.I p.root).hi p.result = .decided p.result

instance (p : ParsedBoundCertificate) : Decidable (MathematicalChecks p) :=
  inferInstanceAs (Decidable (_ ∧ _))

/-- Acceptance is a conjunction of executable tests, not an assumed real conclusion. -/
def accept (expected : ExpectedInstance) (p : ParsedBoundCertificate) : Bool :=
  decide (p.actual = expected.input ∧ p.actual.Positive ∧ MathematicalChecks p)

theorem accept_iff (expected : ExpectedInstance) (p : ParsedBoundCertificate) :
    accept expected p = true ↔
      p.actual = expected.input ∧ p.actual.Positive ∧ MathematicalChecks p := by
  simp [accept]

theorem accepted_instance_eq (expected : ExpectedInstance) (p : ParsedBoundCertificate)
    (h : accept expected p = true) : p.actual = expected.input :=
  ((accept_iff expected p).mp h).1

theorem reject_other_instance (expected : ExpectedInstance) (p : ParsedBoundCertificate)
    (h : p.actual ≠ expected.input) : accept expected p = false := by
  simp [accept, h]

theorem accepted_positive (expected : ExpectedInstance) (p : ParsedBoundCertificate)
    (h : accept expected p = true) : expected.input.Positive := by
  obtain ⟨he, hp, _⟩ := (accept_iff expected p).mp h
  exact he ▸ hp

theorem mathematical_checks_sound (p : ParsedBoundCertificate)
    (h : MathematicalChecks p) : realRound binary64 p.actual.gap = p.result :=
  sql_gap_affine_rounding_soundness binary64 p.actual.A p.actual.B p.actual.I
    p.root h.1 p.result h.2

/-- The conclusion refers to the caller's instance, not arbitrary external A,B,I. -/
theorem accepted_expected_rounding (expected : ExpectedInstance) (p : ParsedBoundCertificate)
    (h : accept expected p = true) :
    realRound binary64 expected.input.gap = p.result := by
  obtain ⟨he, _, hc⟩ := (accept_iff expected p).mp h
  have hr := mathematical_checks_sound p hc
  rw [he] at hr
  exact hr

/-- The explicit absence of a context never activates an unbound fallback. -/
def acceptWithContext (expected : Option ExpectedInstance) (p : ParsedBoundCertificate) : Bool :=
  match expected with
  | none => false
  | some e => accept e p

theorem missing_context_rejected (p : ParsedBoundCertificate) :
    acceptWithContext none p = false := rfl

abbrev BoundParser := List UInt8 → Option ParsedBoundCertificate

/-- The expected context is a separate argument, never obtained from these bytes. -/
def validateBoundPayload (expected : ExpectedInstance) (digest : DigestFunction)
    (parser : BoundParser) (expectedDigest : Digest32) (bytes : List UInt8) :
    Option ParsedBoundCertificate :=
  if digest bytes = expectedDigest then
    match parser bytes with
    | none => none
    | some p => if accept expected p then some p else none
  else none

theorem validate_bound_payload_iff (expected : ExpectedInstance) (digest : DigestFunction)
    (parser : BoundParser) (expectedDigest : Digest32) (bytes : List UInt8)
    (p : ParsedBoundCertificate) :
    validateBoundPayload expected digest parser expectedDigest bytes = some p ↔
      digest bytes = expectedDigest ∧ parser bytes = some p ∧ accept expected p = true := by
  by_cases hd : digest bytes = expectedDigest
  · cases hp : parser bytes with
    | none => simp [validateBoundPayload, hd, hp]
    | some q =>
      by_cases hq : accept expected q = true
      · simp only [validateBoundPayload, if_pos hd, hp, hq, if_true,
          Option.some.injEq]
        constructor
        · intro he
          subst q
          exact ⟨hd, rfl, hq⟩
        · rintro ⟨_, he, _⟩
          exact he
      · simp only [validateBoundPayload, if_pos hd, hp]
        simp only [hq]
        constructor
        · intro h
          cases h
        · rintro ⟨_, he, ha⟩
          cases Option.some.inj he
          exact False.elim (hq ha)
  · simp [validateBoundPayload, hd]

/-- Conditional byte composition; parser/JSON/hash/storage soundness is NOT assumed proved. -/
theorem bound_payload_expected_rounding (expected : ExpectedInstance) (digest : DigestFunction)
    (parser : BoundParser) (expectedDigest : Digest32) (bytes : List UInt8)
    (p : ParsedBoundCertificate)
    (h : validateBoundPayload expected digest parser expectedDigest bytes = some p) :
    p.actual = expected.input ∧ expected.input.Positive ∧
      realRound binary64 expected.input.gap = p.result := by
  have ha := ((validate_bound_payload_iff expected digest parser expectedDigest bytes p).mp h).2.2
  exact ⟨accepted_instance_eq expected p ha, accepted_positive expected p ha,
    accepted_expected_rounding expected p ha⟩

structure NumericSQLExpectedInstanceSuite : Prop where
  binding : ∀ e p, accept e p = true → p.actual = e.input
  refusal : ∀ e p, p.actual ≠ e.input → accept e p = false
  rounding : ∀ e p, accept e p = true → realRound binary64 e.input.gap = p.result
  absent : ∀ p, acceptWithContext none p = false

theorem numeric_sql_expected_instance_master_suite : NumericSQLExpectedInstanceSuite := {
  binding := accepted_instance_eq
  refusal := reject_other_instance
  rounding := accepted_expected_rounding
  absent := missing_context_rejected
}

end NumericSQLExpectedInstance

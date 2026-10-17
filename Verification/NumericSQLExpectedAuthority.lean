/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLSessionBinding

/-! Task-scoped authority gate. Policy, job and observed principal are supplied by
an external supervisor, never decoded from the request. OS identity conformance
and the supervisor's entitlement are explicit external obligations. -/
namespace NumericSQLExpectedAuthority
open NumericSQLExpectedInstance NumericSQLDecisionEnvelope NumericRoundingCertificates

structure Job where
  task : String
  revision : Nat
  executor : Nat
  spec : String

structure Grant where
  issuer : Nat
  task : String
  revision : Nat
  spec : String
  expected : ExpectedInstance

/-- Policy authorizes the complete grant, including its mathematical instance. -/
abbrev Policy := Grant → Bool

def Eligible (policy : Policy) (job : Job) (observed : Nat) (g : Grant) : Prop :=
  policy g = true ∧
  observed = g.issuer ∧ g.issuer ≠ job.executor ∧
  g.task = job.task ∧ g.revision = job.revision ∧ g.spec = job.spec ∧
  job.spec = "sql-gap-binary64-1.0.0"

instance (p : Policy) (j : Job) (o : Nat) (g : Grant) : Decidable (Eligible p j o g) :=
  inferInstanceAs (Decidable (_ ∧ _ ∧ _ ∧ _ ∧ _ ∧ _ ∧ _))

def runAuthorized (policy : Policy) (job : Job) (observed : Nat)
    (grant : Option Grant) (raw : ByteArray) : Envelope :=
  match grant with
  | none => ⟨"", .rejected .invalidContext⟩
  | some g => if Eligible policy job observed g then run (some g.expected) raw
      else ⟨"", .rejected .invalidContext⟩

theorem accepted_authority (policy : Policy) (job : Job) (observed : Nat)
    (g : Grant) (raw : ByteArray) (c : String) (x : SQLInstance)
    (f : FloatRepresentation binary64)
    (h : runAuthorized policy job observed (some g) raw = ⟨c, .accepted x f⟩) :
    Eligible policy job observed g ∧ c = g.expected.contextId ∧
    x = g.expected.input ∧
    NumericRealRounding.realRound binary64 g.expected.input.gap = f := by
  simp only [runAuthorized] at h
  split at h
  · rename_i ha
    exact ⟨ha, accepted_sound _ _ _ _ _ h⟩
  · cases h

theorem missing_grant (p : Policy) (j : Job) (o : Nat) (raw : ByteArray) :
    runAuthorized p j o none raw = ⟨"", .rejected .invalidContext⟩ := rfl

theorem denied_policy (p : Policy) (j : Job) (o : Nat) (g : Grant) (raw : ByteArray)
    (h : p g = false) :
    runAuthorized p j o (some g) raw = ⟨"", .rejected .invalidContext⟩ := by
  simp [runAuthorized, Eligible, h]

theorem executor_cannot_issue (p : Policy) (j : Job) (o : Nat) (g : Grant)
    (raw : ByteArray) (h : g.issuer = j.executor) :
    runAuthorized p j o (some g) raw = ⟨"", .rejected .invalidContext⟩ := by
  simp [runAuthorized, Eligible, h]

theorem other_instance_rejected (p : Policy) (j : Job) (o : Nat) (g : Grant)
    (raw : ByteArray) (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : x ≠ g.expected.input) :
    runAuthorized p j o (some g) raw ≠ ⟨c, .accepted x f⟩ := by
  intro ha
  exact h (accepted_authority _ _ _ _ _ _ _ _ ha).2.2.1

theorem wrong_task_rejected (p : Policy) (j : Job) (o : Nat) (g : Grant)
    (raw : ByteArray) (h : g.task ≠ j.task) :
    runAuthorized p j o (some g) raw = ⟨"", .rejected .invalidContext⟩ := by
  simp [runAuthorized, Eligible, h]

theorem stale_revision_rejected (p : Policy) (j : Job) (o : Nat) (g : Grant)
    (raw : ByteArray) (h : g.revision ≠ j.revision) :
    runAuthorized p j o (some g) raw = ⟨"", .rejected .invalidContext⟩ := by
  simp [runAuthorized, Eligible, h]

end NumericSQLExpectedAuthority

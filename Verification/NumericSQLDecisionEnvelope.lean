/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLCertificateDecoder

/-! Native mathematical response 1.0.0; canonical SQLBT1 bytes, not reconstructed
Python acceptance. Historical full-profile metadata validation is separate. -/
namespace NumericSQLDecisionEnvelope
open NumericSQLExpectedInstance NumericSQLInstanceDecoder NumericSQLCertificateDecoder
open NumericRoundingCertificates

inductive Refusal where
  | invalidContext | invalidInput | invalidWitness
  | instanceMismatch | indeterminate | resourceLimit
  deriving DecidableEq, Repr

def refusalName : Refusal → String
  | .invalidContext => "invalid_context"
  | .invalidInput => "invalid_input"
  | .invalidWitness => "invalid_witness"
  | .instanceMismatch => "instance_mismatch"
  | .indeterminate => "indeterminate"
  | .resourceLimit => "resource_limit"

inductive Decision where
  | rejected (why : Refusal)
  | accepted (actual : SQLInstance) (result : FloatRepresentation binary64)

structure Envelope where
  context : String
  decision : Decision

def classify (why : String) : Refusal :=
  if why = "resource_limit" then .resourceLimit else
  if why = "instance_mismatch" then .instanceMismatch else
  if why = "indeterminate" then .indeterminate else
  if why = "input_decode" then .invalidInput else .invalidWitness

/-- Preserve resource classification lost by the older Option-valued source decoder.
This only diagnoses an already rejected source; it cannot produce acceptance. -/
def inputFailure (t : Tree) : Refusal := Id.run do
  let some src := extract t | return .invalidInput
  for s in [src.A,src.B,src.I] do
    if s.length > 4096 then return .resourceLimit
    let l := NumericSQLDecimalDecoder.lex s.toList
    if !(decide (l.Valid ∧ l.render = s.toList)) then return .invalidInput
    if !(decide (NumericSQLDecimalDecoder.withinLimits l)) then return .resourceLimit
    let q := l.value
    if !(decide (ratBudget q 16384)) then return .resourceLimit
    if !(decide (0 < q)) then return .invalidInput
    let some v := convert src.semantics q | return .invalidInput
    if !(decide (ratBudget v 4096)) then return .resourceLimit
  return .resourceLimit

/-- Context comes from the caller, never from request fields. -/
def run (expected : Option ExpectedInstance) (raw : ByteArray) : Envelope :=
  match expected with
  | none => ⟨"", .rejected .invalidContext⟩
  | some e =>
    match NumericSQLJSONParser.decode raw with
    | .error why => ⟨e.contextId, .rejected
        (if why = "resource_limit" then .resourceLimit else .invalidInput)⟩
    | .ok t =>
      match validateTree e t with
      | .error why => ⟨e.contextId, .rejected
          (if why = "input_decode" then inputFailure t else classify why)⟩
      | .ok p => ⟨e.contextId, .accepted p.actual p.result⟩

theorem accepted_sound (e : ExpectedInstance) (raw : ByteArray)
    (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : run (some e) raw = ⟨c, .accepted x f⟩) :
    c = e.contextId ∧ x = e.input ∧
      NumericRealRounding.realRound binary64 e.input.gap = f := by
  unfold run at h
  cases ht : NumericSQLJSONParser.decode raw with
  | error why => simp [ht] at h
  | ok t =>
    cases hp : validateTree e t with
    | error why => simp [ht,hp] at h
    | ok p =>
      simp only [ht,hp,Envelope.mk.injEq,Decision.accepted.injEq] at h
      obtain ⟨hc,hx,hf⟩ := h
      exact ⟨hc.symm,hx ▸ validated_actual_eq e t p hp,
        hf ▸ (validateTree_sound e t p hp).2.2⟩

theorem missing_context (raw : ByteArray) :
    run none raw = ⟨"", .rejected .invalidContext⟩ := rfl

def ratTree (q : ℚ) : Tree := .object
  [("numerator", .string (toString q.num)),("denominator", .string (toString q.den))]

def instanceTree (x : SQLInstance) : Tree := .object
  [("A",ratTree x.A),("B",ratTree x.B),("I",ratTree x.I),
   ("semantics", .string (match x.semantics with
      | .decimal => "decimal" | .binary64 => "binary64"))]

def status : Decision → String
  | .accepted _ _ => "accepted"
  | .rejected why => refusalName why

def inputTree : Decision → Tree
  | .accepted x _ => instanceTree x
  | .rejected _ => .null

def bitsTree : Decision → Tree
  | .accepted _ f => .string (resultBits f)
  | .rejected _ => .null

/-- Status, instance, result and claim scope are serialized by Lean itself. -/
def toTree (r : Envelope) : Tree := .object
  [("schema", .string "sql-mathematical-reply-1.0.0"),
   ("scope", .string "scalar_sql_rounding_only"),
   ("metadata_policy", .string "not_checked"),
   ("context_id", .string r.context), ("status", .string (status r.decision)),
   ("instance",inputTree r.decision), ("result_bits",bitsTree r.decision)]

theorem accepted_fields (c : String) (x : SQLInstance) (f : FloatRepresentation binary64) :
    field (toTree ⟨c, .accepted x f⟩) "status" = some (.string "accepted") ∧
    field (toTree ⟨c, .accepted x f⟩) "instance" = some (instanceTree x) ∧
    field (toTree ⟨c, .accepted x f⟩) "result_bits" = some (.string (resultBits f)) ∧
    field (toTree ⟨c, .accepted x f⟩) "context_id" = some (.string c) := by
  simp [toTree,field,status,inputTree,bitsTree]

theorem refusal_has_no_result (c : String) (why : Refusal) :
    field (toTree ⟨c, .rejected why⟩) "instance" = some .null ∧
    field (toTree ⟨c, .rejected why⟩) "result_bits" = some .null := by
  simp [toTree,field,inputTree,bitsTree]

/-- Executable resource predicate for the existing codec, without changing it. -/
def admissible : (n : Nat) → (t : Tree) → Decidable (NumericSQLByteTransport.Admissible n t)
  | 0, _ => isFalse (fun h => h)
  | n+1, t => by
    letI (u : Tree) : Decidable (NumericSQLByteTransport.Admissible n u) := admissible n u
    cases t <;> simp only [NumericSQLByteTransport.Admissible] <;> infer_instance

/-- Resource refusal does not fabricate a serialized accepted result. -/
def emit (r : Envelope) : Except Refusal NumericSQLByteTransport.Bytes :=
  let t := toTree r
  letI := admissible 12 t
  if NumericSQLByteTransport.Admissible 12 t then
    let wire := NumericSQLByteTransport.packet t
    if wire.length ≤ 2*1024*1024 then .ok wire else .error .resourceLimit
  else .error .resourceLimit

theorem emit_preserves (r : Envelope) (wire : NumericSQLByteTransport.Bytes)
    (h : emit r = .ok wire) :
    NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree r) := by
  unfold emit at h
  dsimp only at h
  split at h
  next ha =>
    split at h
    next hb =>
      have he := Except.ok.inj h
      rw [← he]
      exact NumericSQLByteTransport.packet_complete 12 (toTree r) ha hb
    next => contradiction
  next => contradiction

/-- Consumer pins context and original input separately and compares exact canonical
bytes, not a hash. It recomputes the mathematical gate; a reply is not an attestation. -/
def consume (e : Option ExpectedInstance) (raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) : Option Envelope :=
  let r := run e raw
  if emit r = .ok wire then some r else none

theorem consumed_eq (e : Option ExpectedInstance) (raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (r : Envelope)
    (h : consume e raw wire = some r) :
    run e raw = r ∧ NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree r) := by
  unfold consume at h
  dsimp only at h
  split at h
  next he =>
    have hr := Option.some.inj h
    exact ⟨hr, hr ▸ emit_preserves (run e raw) wire he⟩
  next => contradiction

theorem consumed_accepted_sound (e : ExpectedInstance) (raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (c : String) (x : SQLInstance)
    (f : FloatRepresentation binary64)
    (h : consume (some e) raw wire = some ⟨c, .accepted x f⟩) :
    c = e.contextId ∧ x = e.input ∧
      NumericRealRounding.realRound binary64 e.input.gap = f ∧
      NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree ⟨c, .accepted x f⟩) := by
  obtain ⟨hr,hw⟩ := consumed_eq (some e) raw wire _ h
  obtain ⟨hc,hx,hf⟩ := accepted_sound e raw c x f hr
  exact ⟨hc,hx,hf,hw⟩

theorem output_tampering_rejected (e : Option ExpectedInstance) (raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (hne : emit (run e raw) ≠ .ok wire) :
    consume e raw wire = none := by simp [consume,hne]

structure NumericSQLDecisionEnvelopeSuite : Prop where
  acceptance : ∀ e raw c x f, run (some e) raw = ⟨c, .accepted x f⟩ →
    c = e.contextId ∧ x = e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = f
  preservation : ∀ r wire, emit r = .ok wire →
    NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree r)
  refusal : ∀ c why, field (toTree ⟨c, .rejected why⟩) "result_bits" = some .null

theorem numeric_sql_decision_envelope_master_suite : NumericSQLDecisionEnvelopeSuite := {
  acceptance := accepted_sound
  preservation := emit_preserves
  refusal := fun c why => (refusal_has_no_result c why).2
}
end NumericSQLDecisionEnvelope

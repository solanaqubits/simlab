/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLControlDecoder

/-! Fixed-context session 1.0.0. Stream IO and caller authorization are external.
The native driver uses these exact transitions and frame checks. -/
namespace NumericSQLSessionBinding
open NumericSQLExpectedInstance NumericSQLDecisionEnvelope NumericRoundingCertificates

structure Session where
  expected : ExpectedInstance
  remaining : Nat

def start (control : ByteArray) (budget : Nat) : Except String Session := do
  let e ← NumericSQLControlDecoder.decode control
  return ⟨e, budget⟩

def step (s : Session) (raw : ByteArray) : Session × Envelope :=
  match s.remaining with
  | 0 => (s, ⟨s.expected.contextId, .rejected .resourceLimit⟩)
  | n+1 => (⟨s.expected, n⟩, run (some s.expected) raw)

theorem step_context (s : Session) (raw : ByteArray) :
    (step s raw).1.expected = s.expected := by
  unfold step
  split <;> rfl

theorem step_budget (s : Session) (raw : ByteArray) :
    (step s raw).1.remaining = s.remaining - 1 := by
  unfold step
  split <;> simp_all

theorem step_accepted (s : Session) (raw : ByteArray) (c : String)
    (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : (step s raw).2 = ⟨c, .accepted x f⟩) :
    c = s.expected.contextId ∧ x = s.expected.input ∧
      NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  unfold step at h
  split at h
  · cases h
  · exact accepted_sound _ _ _ _ _ h

def advance : Session → List ByteArray → Session
  | s, [] => s
  | s, b::bs => advance (step s b).1 bs

theorem sequence_context (s : Session) (bs : List ByteArray) :
    (advance s bs).expected = s.expected := by
  induction bs generalizing s with
  | nil => rfl
  | cons b bs ih => exact (ih _).trans (step_context _ _)

theorem sequence_accepted (s : Session) (bs : List ByteArray) (raw : ByteArray)
    (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : (step (advance s bs) raw).2 = ⟨c, .accepted x f⟩) :
    c = s.expected.contextId ∧ x = s.expected.input ∧
      NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  have r := step_accepted _ _ _ _ _ h
  simpa only [sequence_context] using r

theorem different_instance_rejected (s : Session) (bs : List ByteArray)
    (raw : ByteArray) (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (hx : x ≠ s.expected.input) :
    (step (advance s bs) raw).2 ≠ ⟨c, .accepted x f⟩ := by
  intro h
  exact hx (sequence_accepted _ _ _ _ _ _ h).2.1

theorem exhausted (s : Session) (raw : ByteArray) (h : s.remaining = 0) :
    (step s raw).2 = ⟨s.expected.contextId, .rejected .resourceLimit⟩ := by
  simp [step, h]

/-- No arithmetic with an unbounded length token: header is checked first. -/
def declaredLength (header : List UInt8) : Nat :=
  header.foldl (fun n b => 256*n+b.toNat) 0

def checkFrame (cap : Nat) (header : List UInt8) (body : ByteArray) :
    Except Refusal ByteArray :=
  if header.length ≠ 4 then .error .invalidInput else
  if declaredLength header > cap then .error .resourceLimit else
  if body.size ≠ declaredLength header then .error .invalidInput else .ok body

theorem frame_sound (cap : Nat) (header : List UInt8) (body raw : ByteArray)
    (h : checkFrame cap header body = .ok raw) :
    header.length = 4 ∧ body.size = declaredLength header ∧
      declaredLength header ≤ cap ∧ raw = body := by
  unfold checkFrame at h
  split at h
  · contradiction
  next hh =>
    split at h
    · contradiction
    next hc =>
      split at h
      · contradiction
      next hb =>
        exact ⟨by simpa using hh, by simpa using hb, by omega, (Except.ok.inj h).symm⟩

theorem frame_complete (cap : Nat) (header : List UInt8) (body : ByteArray)
    (hh : header.length = 4) (hb : body.size = declaredLength header)
    (hc : declaredLength header ≤ cap) : checkFrame cap header body = .ok body := by
  simp [checkFrame, hh, hb, Nat.not_lt.mpr hc]

def dispatch (s : Session) (header : List UInt8) (body : ByteArray) : Session × Envelope :=
  match checkFrame 262144 header body with
  | .error why => (s, ⟨s.expected.contextId, .rejected why⟩)
  | .ok raw => step s raw

theorem dispatch_context (s : Session) (header : List UInt8) (body : ByteArray) :
    (dispatch s header body).1.expected = s.expected := by
  unfold dispatch
  split
  · rfl
  · exact step_context _ _

theorem dispatch_accepted (s : Session) (header : List UInt8) (body : ByteArray)
    (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : (dispatch s header body).2 = ⟨c, .accepted x f⟩) :
    header.length = 4 ∧ body.size = declaredLength header ∧
    declaredLength header ≤ 262144 ∧ c = s.expected.contextId ∧
    x = s.expected.input ∧ NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  unfold dispatch at h
  cases hf : checkFrame 262144 header body with
  | error why => simp [hf] at h
  | ok raw =>
    simp only [hf] at h
    obtain ⟨hh, hb, hc, _⟩ := frame_sound _ _ _ _ hf
    exact ⟨hh, hb, hc, step_accepted _ _ _ _ _ h⟩

def consume (s : Session) (header : List UInt8) (body : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) : Option (Session × Envelope) :=
  let r := dispatch s header body
  if emit r.2 = .ok wire then some r else none

theorem consume_sound (s : Session) (header : List UInt8) (body : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (next : Session) (c : String)
    (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : consume s header body wire = some (next, ⟨c, .accepted x f⟩)) :
    next.expected = s.expected ∧ x = s.expected.input ∧
    NumericRealRounding.realRound binary64 s.expected.input.gap = f ∧
    NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree ⟨c, .accepted x f⟩) := by
  unfold consume at h
  dsimp only at h
  split at h
  next hw =>
    have hr := Option.some.inj h
    have he := congrArg Prod.snd hr
    have hc := dispatch_context s header body
    rw [hr] at hc
    have hs := dispatch_accepted s header body c x f he
    have hw2 := emit_preserves _ _ hw
    rw [he] at hw2
    exact ⟨hc, hs.2.2.2.2.1, hs.2.2.2.2.2, hw2⟩
  · contradiction

theorem start_sound (control : ByteArray) (budget : Nat) (s : Session)
    (h : start control budget = .ok s) :
    ∃ t, NumericSQLJSONGrammar.Represents 64 control.data.toList t ∧
      NumericSQLControlDecoder.ContextRep t s.expected := by
  unfold start at h
  cases hd : NumericSQLControlDecoder.decode control with
  | error why => simp [hd, bind, Except.bind] at h
  | ok e =>
    simp only [hd, bind, Except.bind, pure, Except.pure] at h
    cases Except.ok.inj h
    exact NumericSQLControlDecoder.decode_sound _ _ hd

theorem original_control_accepted (control : ByteArray) (budget : Nat) (s : Session)
    (hs : start control budget = .ok s) (bs : List ByteArray) (raw : ByteArray)
    (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : (step (advance s bs) raw).2 = ⟨c, .accepted x f⟩) :
    ∃ t, NumericSQLJSONGrammar.Represents 64 control.data.toList t ∧
      NumericSQLControlDecoder.ContextRep t s.expected ∧ c = s.expected.contextId ∧
      x = s.expected.input ∧ NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  obtain ⟨t, ht, he⟩ := start_sound _ _ _ hs
  exact ⟨t, ht, he, sequence_accepted _ _ _ _ _ _ h⟩

structure NumericSQLSessionBindingSuite : Prop where
  fixed : ∀ s bs, (advance s bs).expected = s.expected
  framed : ∀ cap header body raw, checkFrame cap header body = .ok raw →
    header.length = 4 ∧ body.size = declaredLength header ∧
      declaredLength header ≤ cap ∧ raw = body
  sound : ∀ s raw c x f, (step s raw).2 = ⟨c, .accepted x f⟩ →
    c = s.expected.contextId ∧ x = s.expected.input ∧
      NumericRealRounding.realRound binary64 s.expected.input.gap = f

theorem numeric_sql_session_binding_master_suite : NumericSQLSessionBindingSuite :=
  ⟨sequence_context, frame_sound, step_accepted⟩
end NumericSQLSessionBinding

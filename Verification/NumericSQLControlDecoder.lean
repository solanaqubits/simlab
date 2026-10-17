/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLDecisionEnvelope

/-! Control profile sql-trusted-context-2.0.0. Original control bytes are parsed by
our existing proved JSON parser. Provenance of this separate caller channel is external. -/
namespace NumericSQLControlDecoder
open NumericSQLInstanceDecoder NumericSQLExpectedInstance NumericSQLDecisionEnvelope
open NumericRoundingCertificates NumericSQLJSONGrammar

def decimalValue (s : String) : Nat :=
  s.toList.foldl (fun n c => n * 10 + (c.toNat - '0'.toNat)) 0

/-- Base-ten semantics, grammar and finite input budget, not a decoder equality. -/
def NatRep (s : String) (n : Nat) : Prop :=
  s.isEmpty = false ∧ s.toList.all NumericSQLDecimalDecoder.digit = true ∧
  s.length ≤ 1300 ∧ n = decimalValue s ∧ bits n ≤ 4096

def readNat (s : String) : Except String Nat :=
  if s.length > 1300 then .error "resource_limit" else
  if s.isEmpty || !(s.toList.all NumericSQLDecimalDecoder.digit) then
    .error "context_integer" else
  let n := decimalValue s
  if bits n > 4096 then .error "resource_limit" else .ok n

theorem readNat_sound (s : String) (n : Nat) (h : readNat s = .ok n) : NatRep s n := by
  unfold readNat at h
  split at h
  · contradiction
  next hl =>
    split at h
    · contradiction
    next hs =>
      dsimp only at h
      split at h
      · contradiction
      next hb =>
        have hn := Except.ok.inj h
        subst n
        simp only [Bool.or_eq_true, Bool.not_eq_true, not_or] at hs
        exact ⟨by simpa using hs.1, by simpa using hs.2, by omega, rfl, by omega⟩

theorem readNat_complete (s : String) (n : Nat) (h : NatRep s n) : readNat s = .ok n := by
  rcases h with ⟨he,hd,hl,rfl,hb⟩
  simp [readNat,he,hd,Nat.not_lt.mpr hl,Nat.not_lt.mpr hb]

/-- Positive exact ratios; equivalent unreduced spellings are permitted. -/
def RatRep (t : Tree) (q : ℚ) : Prop :=
  keys t ["numerator","denominator"] = true ∧
  ∃ ns ds n d, stringField t "numerator" = some ns ∧
    stringField t "denominator" = some ds ∧ NatRep ns n ∧ NatRep ds d ∧
    0 < n ∧ 0 < d ∧ q = (n : ℚ) / (d : ℚ)

def readRat (t : Tree) : Except String ℚ :=
  if !(keys t ["numerator","denominator"]) then .error "context_rational_shape" else do
  let some ns := stringField t "numerator" | throw "context_numerator"
  let some ds := stringField t "denominator" | throw "context_denominator"
  let n ← readNat ns
  let d ← readNat ds
  if n = 0 ∨ d = 0 then .error "context_positive_domain"
  else .ok ((n : ℚ) / (d : ℚ))

theorem readRat_sound (t : Tree) (q : ℚ) (h : readRat t = .ok q) : RatRep t q := by
  unfold readRat at h
  split at h
  · contradiction
  next hk =>
    cases hn : stringField t "numerator" with
    | none => simp [hn] at h
    | some ns =>
      cases hd : stringField t "denominator" with
      | none => simp [hn,hd] at h
      | some ds =>
        cases hnv : readNat ns with
        | error e => simp [hn,hd,hnv,bind,Except.bind] at h
        | ok n =>
          cases hdv : readNat ds with
          | error e => simp [hn,hd,hnv,hdv,bind,Except.bind] at h
          | ok d =>
            simp only [hn,hd,hnv,hdv,bind,Except.bind] at h
            split at h
            · contradiction
            next hp =>
              exact ⟨by simpa using hk,ns,ds,n,d,hn,hd,
                readNat_sound _ _ hnv,readNat_sound _ _ hdv,by omega,by omega,
                (Except.ok.inj h).symm⟩

theorem readRat_complete (t : Tree) (q : ℚ) (h : RatRep t q) : readRat t = .ok q := by
  rcases h with ⟨hk,ns,ds,n,d,hn,hd,hnv,hdv,hp,hq,rfl⟩
  simp [readRat,hk,hn,hd,readNat_complete _ _ hnv,readNat_complete _ _ hdv,
    bind,Except.bind,Nat.ne_of_gt hp,Nat.ne_of_gt hq]

theorem rational_positive (t : Tree) (q : ℚ) (h : RatRep t q) : 0 < q := by
  rcases h with ⟨_,_,_,n,d,_,_,_,_,hn,hd,rfl⟩
  exact div_pos (by exact_mod_cast hn) (by exact_mod_cast hd)

def semanticsName : InputSemantics → String
  | .decimal => "decimal" | .binary64 => "binary64"

def InstanceRep (t : Tree) (x : SQLInstance) : Prop :=
  keys t ["A","B","I","semantics"] = true ∧
  stringField t "semantics" = some (semanticsName x.semantics) ∧
  ∃ a b i, field t "A" = some a ∧ field t "B" = some b ∧ field t "I" = some i ∧
    RatRep a x.A ∧ RatRep b x.B ∧ RatRep i x.I

def readSemantics (s : String) : Except String InputSemantics :=
  if s = "decimal" then .ok .decimal else
    if s = "binary64" then .ok .binary64 else .error "context_semantics"

theorem readSemantics_sound (s : String) (m : InputSemantics)
    (h : readSemantics s = .ok m) : s = semanticsName m := by
  unfold readSemantics at h
  split at h
  next hs => cases Except.ok.inj h; exact hs
  next =>
    split at h
    next hs => cases Except.ok.inj h; exact hs
    next => contradiction

theorem readSemantics_complete (m : InputSemantics) :
    readSemantics (semanticsName m) = .ok m := by cases m <;> decide +kernel

def readInstance (t : Tree) : Except String SQLInstance :=
  if !(keys t ["A","B","I","semantics"]) then .error "context_instance_shape" else do
  let some sem := stringField t "semantics" | throw "context_semantics"
  let mode ← readSemantics sem
  let some a := field t "A" | throw "context_A"
  let some b := field t "B" | throw "context_B"
  let some i := field t "I" | throw "context_I"
  let av ← readRat a
  let bv ← readRat b
  let iv ← readRat i
  .ok ⟨av,bv,iv,mode⟩


theorem readInstance_sound (t : Tree) (x : SQLInstance)
    (h : readInstance t = .ok x) : InstanceRep t x := by
  unfold readInstance at h
  split at h
  · contradiction
  next hk =>
    cases hs : stringField t "semantics" with
    | none => simp [hs] at h
    | some s =>
      cases hm : readSemantics s with
      | error e => simp [hs,hm,bind,Except.bind] at h
      | ok m =>
        cases ha : field t "A" with
        | none => simp [hs,hm,ha,bind,Except.bind] at h
        | some a =>
          cases hb : field t "B" with
          | none => simp [hs,hm,ha,hb,bind,Except.bind] at h
          | some b =>
            cases hi : field t "I" with
            | none => simp [hs,hm,ha,hb,hi,bind,Except.bind] at h
            | some i =>
              cases hav : readRat a with
              | error e => simp [hs,hm,ha,hb,hi,hav,bind,Except.bind] at h
              | ok av =>
                cases hbv : readRat b with
                | error e => simp [hs,hm,ha,hb,hi,hav,hbv,bind,Except.bind] at h
                | ok bv =>
                  cases hiv : readRat i with
                  | error e => simp [hs,hm,ha,hb,hi,hav,hbv,hiv,bind,Except.bind] at h
                  | ok iv =>
                    simp only [hs,hm,ha,hb,hi,hav,hbv,hiv,bind,Except.bind] at h
                    cases Except.ok.inj h
                    exact ⟨by simpa using hk, by simpa [readSemantics_sound _ _ hm] using hs,
                      a,b,i,ha,hb,hi,readRat_sound _ _ hav,readRat_sound _ _ hbv,
                      readRat_sound _ _ hiv⟩

theorem readInstance_complete (t : Tree) (x : SQLInstance) (h : InstanceRep t x) :
    readInstance t = .ok x := by
  rcases h with ⟨hk,hs,a,b,i,ha,hb,hi,hav,hbv,hiv⟩
  simp [readInstance,hk,hs,readSemantics_complete,ha,hb,hi,readRat_complete _ _ hav,
    readRat_complete _ _ hbv,readRat_complete _ _ hiv,bind,Except.bind]

/-- Exact shape, literal version, identifier and independently specified input values. -/
def ContextRep (t : Tree) (e : ExpectedInstance) : Prop :=
  keys t ["schema","context_id","input"] = true ∧
  stringField t "schema" = some "sql-trusted-context-2.0.0" ∧
  stringField t "context_id" = some e.contextId ∧
  e.contextId.isEmpty = false ∧ e.contextId.length ≤ 128 ∧
  ∃ u, field t "input" = some u ∧ InstanceRep u e.input

def decodeTree (t : Tree) : Except String ExpectedInstance :=
  if !(keys t ["schema","context_id","input"]) then .error "context_shape" else
  if stringField t "schema" != some "sql-trusted-context-2.0.0" then
    .error "context_version" else do
  let some id := stringField t "context_id" | throw "context_id"
  if id.isEmpty then .error "context_id" else
  if id.length > 128 then .error "resource_limit" else do
  let some u := field t "input" | throw "context_input"
  let x ← readInstance u
  .ok ⟨id,x⟩

theorem decodeTree_sound (t : Tree) (e : ExpectedInstance)
    (h : decodeTree t = .ok e) : ContextRep t e := by
  unfold decodeTree at h
  split at h
  · contradiction
  next hk =>
    split at h
    · contradiction
    next hv =>
      cases hid : stringField t "context_id" with
      | none => simp [hid] at h
      | some id =>
        simp only [hid] at h
        split at h
        · contradiction
        next he =>
          split at h
          · contradiction
          next hl =>
            cases hu : field t "input" with
            | none => simp [hu] at h
            | some u =>
              cases hx : readInstance u with
              | error err => simp [hu,hx,bind,Except.bind] at h
              | ok x =>
                simp only [hu,hx,bind,Except.bind] at h
                cases Except.ok.inj h
                exact ⟨by simpa using hk,by simpa using hv,hid,by simpa using he,
                  by dsimp; omega,u,hu,readInstance_sound _ _ hx⟩

theorem decodeTree_complete (t : Tree) (e : ExpectedInstance) (h : ContextRep t e) :
    decodeTree t = .ok e := by
  rcases h with ⟨hk,hv,hi,he,hl,u,hu,hx⟩
  simp [decodeTree,hk,hv,hi,he,Nat.not_lt.mpr hl,hu,readInstance_complete _ _ hx,
    bind,Except.bind]

theorem decodeTree_unique (t : Tree) (e f : ExpectedInstance)
    (he : ContextRep t e) (hf : ContextRep t f) : e = f :=
  Except.ok.inj ((decodeTree_complete t e he).symm.trans (decodeTree_complete t f hf))

theorem equivalent_representations (t u : Tree) (e : ExpectedInstance)
    (ht : ContextRep t e) (hu : ContextRep u e) : decodeTree t = decodeTree u := by
  rw [decodeTree_complete _ _ ht,decodeTree_complete _ _ hu]

/-- Original control bytes use the same proved parser as the original request. -/
def decode (bs : ByteArray) : Except String ExpectedInstance :=
  if bs.size > 16384 then .error "resource_limit" else do
  let t ← NumericSQLJSONParser.decode bs
  decodeTree t

theorem decode_sound (bs : ByteArray) (e : ExpectedInstance) (h : decode bs = .ok e) :
    ∃ t, Represents 64 bs.data.toList t ∧ ContextRep t e := by
  unfold decode at h
  split at h
  · contradiction
  next =>
    cases ht : NumericSQLJSONParser.decode bs with
    | error err => simp [ht,bind,Except.bind] at h
    | ok t =>
      simp only [ht,bind,Except.bind] at h
      exact ⟨t,NumericSQLJSONParser.decode_sound _ _ ht,decodeTree_sound _ _ h⟩

def runControl (control raw : ByteArray) : Envelope :=
  match decode control with
  | .error reason => ⟨"", .rejected
      (if reason = "resource_limit" then .resourceLimit else .invalidContext)⟩
  | .ok e => run (some e) raw

theorem accepted_control_sound (control raw : ByteArray) (c : String)
    (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : runControl control raw = ⟨c, .accepted x f⟩) :
    ∃ e t, Represents 64 control.data.toList t ∧ ContextRep t e ∧
      c = e.contextId ∧ x = e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = f := by
  unfold runControl at h
  cases hd : decode control with
  | error err => simp [hd] at h
  | ok e =>
    simp only [hd] at h
    obtain ⟨t,ht,he⟩ := decode_sound control e hd
    obtain ⟨hc,hx,hf⟩ := accepted_sound e raw c x f h
    exact ⟨e,t,ht,he,hc,hx,hf⟩

def consumeControl (control raw : ByteArray) (wire : NumericSQLByteTransport.Bytes) :
    Option Envelope :=
  let r := runControl control raw
  if emit r = .ok wire then some r else none

theorem consumed_control_sound (control raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (c : String) (x : SQLInstance)
    (f : FloatRepresentation binary64)
    (h : consumeControl control raw wire = some ⟨c, .accepted x f⟩) :
    ∃ e t, Represents 64 control.data.toList t ∧ ContextRep t e ∧ c = e.contextId ∧
      x = e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = f ∧
      NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree ⟨c, .accepted x f⟩) := by
  unfold consumeControl at h
  dsimp only at h
  split at h
  next hw =>
    have hr := Option.some.inj h
    obtain ⟨e,t,ht,he,hc,hx,hf⟩ := accepted_control_sound control raw c x f hr
    exact ⟨e,t,ht,he,hc,hx,hf,hr ▸ emit_preserves _ _ hw⟩
  next => contradiction

theorem decoded_positive (bs : ByteArray) (e : ExpectedInstance)
    (h : decode bs = .ok e) : e.input.Positive := by
  obtain ⟨t,_,_,_,_,_,_,u,_,_,_,a,b,i,_,_,_,ha,hb,hi⟩ := decode_sound bs e h
  exact ⟨rational_positive _ _ ha,rational_positive _ _ hb,rational_positive _ _ hi⟩

theorem decode_unique (bs : ByteArray) (e f : ExpectedInstance)
    (he : decode bs = .ok e) (hf : decode bs = .ok f) : e = f :=
  Except.ok.inj (he.symm.trans hf)

/-- Different parameters cannot be accepted even when their rounded bits coincide. -/
theorem different_instance_rejected (control raw : ByteArray) (e : ExpectedInstance)
    (hd : decode control = .ok e) (c : String) (other : SQLInstance)
    (f : FloatRepresentation binary64) (hne : other ≠ e.input) :
    runControl control raw ≠ ⟨c, .accepted other f⟩ := by
  intro h
  have hr : run (some e) raw = ⟨c, .accepted other f⟩ := by simpa [runControl,hd] using h
  exact hne (accepted_sound e raw c other f hr).2.1

structure NumericSQLControlDecoderSuite : Prop where
  ast_sound : ∀ t e, decodeTree t = .ok e → ContextRep t e
  ast_complete : ∀ t e, ContextRep t e → decodeTree t = .ok e
  byte_sound : ∀ bs e, decode bs = .ok e →
    ∃ t, Represents 64 bs.data.toList t ∧ ContextRep t e

theorem numeric_sql_control_decoder_master_suite : NumericSQLControlDecoderSuite := {
  ast_sound := decodeTree_sound
  ast_complete := decodeTree_complete
  byte_sound := decode_sound
}
end NumericSQLControlDecoder

/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLSessionBinding

/-! Exact bounded chunk assembly. OS delivery is an external event source, not an axiom
about the numerical result. The native IO loop calls these executable transitions. -/
namespace NumericSQLStreamReader
open NumericSQLSessionBinding NumericSQLDecisionEnvelope NumericSQLExpectedInstance
open NumericRoundingCertificates
abbrev Bytes := List UInt8

inductive ReadError where
  | eof | truncated | invalidChunk | resourceLimit
  deriving DecidableEq, Repr

structure Collector where
  target : Nat
  bytes : Bytes
  deriving DecidableEq, Repr

def remaining (s : Collector) : Nat := s.target - s.bytes.length

def feed (s : Collector) (chunk : Bytes) : Except ReadError Collector :=
  if s.bytes.length > s.target then .error .invalidChunk else
  if chunk.isEmpty then .error .invalidChunk else
  if chunk.length > remaining s then .error .invalidChunk else
    .ok ⟨s.target, s.bytes ++ chunk⟩

theorem feed_sound (s t : Collector) (b : Bytes) (h : feed s b = .ok t) :
    t.target = s.target ∧ t.bytes = s.bytes ++ b ∧
    t.bytes.length ≤ t.target ∧ b ≠ [] ∧ b.length ≤ remaining s := by
  unfold feed at h
  split at h
  · contradiction
  next hs =>
    split at h
    · contradiction
    next hb =>
      split at h
      · contradiction
      next hl =>
        cases Except.ok.inj h
        refine ⟨rfl, rfl, ?_, ?_, ?_⟩
        · simp only [List.length_append]
          unfold remaining at hl
          omega
        · simpa using hb
        · omega

theorem feed_complete (s : Collector) (b : Bytes)
    (hs : s.bytes.length ≤ s.target) (hb : b ≠ [])
    (hl : b.length ≤ remaining s) : feed s b = .ok ⟨s.target, s.bytes ++ b⟩ := by
  simp [feed, Nat.not_lt.mpr hs, List.isEmpty_iff, hb, Nat.not_lt.mpr hl]

theorem feed_progress (s t : Collector) (b : Bytes) (h : feed s b = .ok t) :
    remaining t < remaining s := by
  obtain ⟨ht, hv, hl, hb, _⟩ := feed_sound s t b h
  have hp : 0 < b.length := by cases b <;> simp_all
  simp only [remaining, ht, hv, List.length_append] at *
  omega

def collect : Collector → List Bytes → Except ReadError Collector
  | s, [] => .ok s
  | s, b :: bs => do
    let t ← feed s b
    collect t bs

theorem collect_complete (s : Collector) (chunks : List Bytes)
    (hp : ∀ b ∈ chunks, b ≠ [])
    (hl : s.bytes.length + chunks.flatten.length ≤ s.target) :
    collect s chunks = .ok ⟨s.target, s.bytes ++ chunks.flatten⟩ := by
  induction chunks generalizing s with
  | nil => simp [collect]
  | cons b bs ih =>
    have hb := hp b (by simp)
    have ht : s.bytes.length ≤ s.target := by
      simp only [List.flatten_cons, List.length_append] at hl
      omega
    have hn : b.length ≤ remaining s := by
      simp only [List.flatten_cons, List.length_append] at hl
      unfold remaining
      omega
    have hh := feed_complete s b ht hb hn
    simp only [collect, hh, bind, Except.bind]
    rw [ih]
    · simp [List.flatten_cons, List.append_assoc]
    · intro a ha; exact hp a (by simp [ha])
    · simpa [List.flatten_cons, List.length_append, Nat.add_assoc] using hl

theorem collect_sound (s t : Collector) (chunks : List Bytes)
    (hs : s.bytes.length ≤ s.target) (h : collect s chunks = .ok t) :
    t.target = s.target ∧ t.bytes = s.bytes ++ chunks.flatten ∧
    t.bytes.length ≤ t.target := by
  induction chunks generalizing s with
  | nil => simp only [collect, Except.ok.injEq] at h; subst t; simp [hs]
  | cons b bs ih =>
    cases hf : feed s b with
    | error e => simp [collect, hf, bind, Except.bind] at h
    | ok u =>
      simp only [collect, hf, bind, Except.bind] at h
      obtain ⟨ht, hv, hu, _, _⟩ := feed_sound s u b hf
      obtain ⟨h1, h2, h3⟩ := ih u hu h
      exact ⟨h1.trans ht, by simpa [hv, List.flatten_cons, List.append_assoc] using h2, h3⟩

inductive Event where
  | data (bytes : Bytes) | eof
  deriving DecidableEq, Repr
inductive Machine where
  | active (collector : Collector) | done (bytes : Bytes) | failed (why : ReadError)
  deriving DecidableEq, Repr

def settle (s : Collector) : Machine :=
  if s.bytes.length = s.target then .done s.bytes else .active s

def initial (target : Nat) : Machine := settle ⟨target, []⟩

def advance (cleanEOF : Bool) (m : Machine) (event : Event) : Machine :=
  match m with
  | .done b => .done b
  | .failed e => .failed e
  | .active s =>
    match event with
    | .eof => .failed (if cleanEOF && s.bytes.isEmpty then .eof else .truncated)
    | .data b =>
      match feed s b with
      | .error e => .failed e
      | .ok t => settle t

def replay (cleanEOF : Bool) : Machine → List Event → Machine
  | m, [] => m
  | m, e :: es => replay cleanEOF (advance cleanEOF m e) es

theorem failed_absorbing (c : Bool) (why : ReadError) (es : List Event) :
    replay c (.failed why) es = .failed why := by
  induction es with
  | nil => rfl
  | cons e es ih => simpa [replay, advance] using ih

theorem done_absorbing (c : Bool) (b : Bytes) (es : List Event) :
    replay c (.done b) es = .done b := by
  induction es with
  | nil => rfl
  | cons e es ih => simpa [replay, advance] using ih

theorem data_step (c : Bool) (s : Collector) (b : Bytes)
    (hp : b ≠ []) (hl : s.bytes.length + b.length ≤ s.target) :
    advance c (settle s) (.data b) = settle ⟨s.target, s.bytes ++ b⟩ := by
  have hb : 0 < b.length := by cases b <;> simp_all
  have hs : s.bytes.length ≤ s.target := by omega
  have hn : b.length ≤ remaining s := by unfold remaining; omega
  have hne : s.bytes.length ≠ s.target := by omega
  simp [settle, hne, advance, feed_complete s b hs hp hn]

theorem partition_semantics (c : Bool) (s : Collector) (chunks : List Bytes)
    (hp : ∀ b ∈ chunks, b ≠ [])
    (hl : s.bytes.length + chunks.flatten.length ≤ s.target) :
    replay c (settle s) (chunks.map Event.data) =
      settle ⟨s.target, s.bytes ++ chunks.flatten⟩ := by
  induction chunks generalizing s with
  | nil => simp [replay]
  | cons b bs ih =>
    have hb := hp b (by simp)
    have hn : s.bytes.length + b.length ≤ s.target := by
      simp only [List.flatten_cons, List.length_append] at hl; omega
    simp only [List.map_cons, replay, data_step c s b hb hn]
    rw [ih]
    · simp [List.flatten_cons, List.append_assoc]
    · intro a ha; exact hp a (by simp [ha])
    · simpa [List.flatten_cons, List.length_append, Nat.add_assoc] using hl

theorem partition_complete (c : Bool) (target : Nat) (chunks : List Bytes)
    (hp : ∀ b ∈ chunks, b ≠ []) (hl : chunks.flatten.length = target) :
    replay c (initial target) (chunks.map Event.data) = .done chunks.flatten := by
  have h := partition_semantics c ⟨target, []⟩ chunks hp (by simp [hl])
  simpa [initial, settle, hl] using h

theorem fragmentation_independent (c : Bool) (target : Nat) (a b : List Bytes)
    (ha : ∀ x ∈ a, x ≠ []) (hb : ∀ x ∈ b, x ≠ [])
    (he : a.flatten = b.flatten) (hl : a.flatten.length = target) :
    replay c (initial target) (a.map Event.data) =
      replay c (initial target) (b.map Event.data) := by
  rw [partition_complete c target a ha hl,
    partition_complete c target b hb (by rw [← he]; exact hl), he]

def Valid (target : Nat) : Machine → Prop
  | .active s => s.target = target ∧ s.bytes.length < target
  | .done b => b.length = target
  | .failed _ => True

theorem settle_valid (s : Collector) (h : s.bytes.length ≤ s.target) :
    Valid s.target (settle s) := by
  unfold settle
  split
  · assumption
  · exact ⟨rfl, by omega⟩

theorem advance_valid (c : Bool) (m : Machine) (event : Event) (n : Nat)
    (h : Valid n m) : Valid n (advance c m event) := by
  cases m with
  | done b => exact h
  | failed why => trivial
  | active s =>
    obtain ⟨ht, _⟩ := h
    cases event with
    | eof => trivial
    | data b =>
      cases hf : feed s b with
      | error why => simp [advance, hf, Valid]
      | ok t =>
        obtain ⟨hn, _, hv, _, _⟩ := feed_sound s t b hf
        simpa [advance, hf, ← ht, ← hn] using settle_valid t hv

def eventBytes : Event → Bytes
  | .data b => b
  | .eof => []

/-- A completed result is a prefix of observed bytes, never invented or reordered. -/
def Provenance (observed : Bytes) : Machine → Prop
  | .active s => s.bytes = observed
  | .done b => ∃ tail, observed = b ++ tail
  | .failed _ => True

theorem settle_provenance (s : Collector) : Provenance s.bytes (settle s) := by
  unfold settle
  split
  · exact ⟨[], by simp⟩
  · rfl

theorem advance_provenance (c : Bool) (m : Machine) (event : Event) (seen : Bytes)
    (h : Provenance seen m) :
    Provenance (seen ++ eventBytes event) (advance c m event) := by
  cases m with
  | failed why => trivial
  | done b =>
    obtain ⟨tail, ht⟩ := h
    exact ⟨tail ++ eventBytes event, by simp [ht, List.append_assoc]⟩
  | active s =>
    cases event with
    | eof => trivial
    | data b =>
      cases hf : feed s b with
      | error why => simp [advance, hf, Provenance]
      | ok t =>
        have hv := (feed_sound s t b hf).2.1
        have he : t.bytes = seen ++ b := hv.trans (congrArg (· ++ b) h)
        simpa only [advance, hf, eventBytes, ← he] using settle_provenance t

theorem replay_provenance (c : Bool) (m : Machine) (events : List Event) (seen : Bytes)
    (h : Provenance seen m) :
    Provenance (seen ++ (events.map eventBytes).flatten) (replay c m events) := by
  induction events generalizing m seen with
  | nil => simpa [replay] using h
  | cons e es ih =>
    have hr := ih (advance c m e) (seen ++ eventBytes e) (advance_provenance c m e seen h)
    simpa [replay, List.append_assoc] using hr

theorem replay_valid (c : Bool) (m : Machine) (events : List Event) (n : Nat)
    (h : Valid n m) : Valid n (replay c m events) := by
  induction events generalizing m with
  | nil => exact h
  | cons e es ih => exact ih _ (advance_valid c m e n h)

theorem completed_exact (c : Bool) (n : Nat) (events : List Event) (b : Bytes)
    (h : replay c (initial n) events = .done b) :
    b.length = n ∧ ∃ tail, (events.map eventBytes).flatten = b ++ tail := by
  have hi : Valid n (initial n) := settle_valid ⟨n, []⟩ (by simp)
  have hp : Provenance [] (initial n) := settle_provenance ⟨n, []⟩
  have hv := replay_valid c _ events n hi
  have hh := replay_provenance c _ events [] hp
  simpa [h, Valid, Provenance] using And.intro hv hh

theorem header_eof : advance true (initial 4) .eof = .failed .eof := by decide

theorem partial_eof (c : Bool) (s : Collector) (hp : s.bytes ≠ []) :
    advance c (.active s) .eof = .failed .truncated := by
  simp [advance, List.isEmpty_iff, hp]

theorem body_eof (s : Collector) :
    advance false (.active s) .eof = .failed .truncated := by simp [advance]

def frameResult (cap : Nat) (header body : Bytes) : Except Refusal (Bytes × ByteArray) := do
  let raw ← checkFrame cap header ⟨body.toArray⟩
  return (header, raw)

theorem frame_result_sound (cap : Nat) (header body h : Bytes) (raw : ByteArray)
    (hf : frameResult cap header body = .ok (h, raw)) :
    h = header ∧ raw.data.toList = body ∧ header.length = 4 ∧
    body.length = declaredLength header ∧ declaredLength header ≤ cap := by
  unfold frameResult at hf
  cases hc : checkFrame cap header ⟨body.toArray⟩ with
  | error e => simp [hc, bind, Except.bind] at hf
  | ok b =>
    simp only [hc, bind, Except.bind, pure, Except.pure, Except.ok.injEq,
      Prod.mk.injEq] at hf
    obtain ⟨hh, hb, hl, he⟩ := frame_sound _ _ _ _ hc
    obtain ⟨rfl, rfl⟩ := hf
    subst b
    exact ⟨rfl, by simp, hh, by simpa [ByteArray.size] using hb, hl⟩

/-- Full composition uses the assembled bytes themselves, not another input copy. -/
theorem framed_rounding (s : Session) (header body h : Bytes) (raw : ByteArray)
    (hf : frameResult 262144 header body = .ok (h, raw)) (c : String)
    (x : SQLInstance) (f : FloatRepresentation binary64)
    (ha : (dispatch s h raw).2 = ⟨c, .accepted x f⟩) :
    raw.data.toList = body ∧ x = s.expected.input ∧
      NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  have hb := frame_result_sound _ _ _ _ _ hf
  have hr := dispatch_accepted _ _ _ _ _ _ ha
  exact ⟨hb.2.1, hr.2.2.2.2.1, hr.2.2.2.2.2⟩

theorem stream_rounding (s : Session) (hs bs : List Event) (header body h : Bytes)
    (raw : ByteArray) (hh : replay true (initial 4) hs = .done header)
    (hb : replay false (initial (declaredLength header)) bs = .done body)
    (hf : frameResult 262144 header body = .ok (h, raw)) (c : String)
    (x : SQLInstance) (f : FloatRepresentation binary64)
    (ha : (dispatch s h raw).2 = ⟨c, .accepted x f⟩) :
    header.length = 4 ∧ body.length = declaredLength header ∧
    (∃ tail, (hs.map eventBytes).flatten = header ++ tail) ∧
    (∃ tail, (bs.map eventBytes).flatten = body ++ tail) ∧
    raw.data.toList = body ∧ x = s.expected.input ∧
    NumericRealRounding.realRound binary64 s.expected.input.gap = f := by
  have h1 := completed_exact _ _ _ _ hh
  have h2 := completed_exact _ _ _ _ hb
  exact ⟨h1.1, h2.1, h1.2, h2.2, framed_rounding _ _ _ _ _ hf _ _ _ ha⟩

structure NumericSQLStreamReaderSuite : Prop where
  exact_chunks : ∀ s t chunks, s.bytes.length ≤ s.target → collect s chunks = .ok t →
    t.target = s.target ∧ t.bytes = s.bytes ++ chunks.flatten ∧ t.bytes.length ≤ t.target
  complete_chunks : ∀ (c : Bool) (target : Nat) (chunks : List Bytes), (∀ b ∈ chunks, b ≠ []) →
    chunks.flatten.length = target →
    replay c (initial target) (chunks.map Event.data) = .done chunks.flatten
  fail_stop : ∀ c why es, replay c (.failed why) es = .failed why

theorem numeric_sql_stream_reader_master_suite : NumericSQLStreamReaderSuite :=
  ⟨collect_sound, partition_complete, failed_absorbing⟩
end NumericSQLStreamReader

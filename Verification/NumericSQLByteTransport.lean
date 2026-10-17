/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLASTTransport

/-! SQLBT1: canonical binary transport, separate from the historical tagged JSON format.
Proofs start at exact UInt8 lists. UTF-8 validity uses Lean's checked String representation.
The outer IO driver, Python serializer and original request JSON remain separate obligations. -/
namespace NumericSQLByteTransport
open NumericSQLInstanceDecoder NumericSQLExpectedInstance
abbrev Bytes := List UInt8

def word (n : Nat) : Bytes := [UInt8.ofNat (n / 256), UInt8.ofNat n]
def utf8 (s : String) : Bytes := s.toUTF8.data.toList
def text (s : String) : Bytes := word (utf8 s).length ++ utf8 s

def encode : Tree → Bytes
  | .null => [0]
  | .bool false => [1]
  | .bool true => [2]
  | .number s => 3 :: text s
  | .string s => 4 :: text s
  | .array ts => 5 :: (word ts.length ++ ts.flatMap encode)
  | .object fs => 6 :: (word fs.length ++ fs.flatMap fun p => text p.1 ++ encode p.2)
termination_by t => sizeOf t
decreasing_by
  all_goals simp_wf
  · decreasing_trivial
  · have h := List.sizeOf_lt_of_mem ‹_ ∈ _›
    cases p
    simp_all only [Prod.mk.sizeOf_spec]
    omega

def readWord : Bytes → Except String (Nat × Bytes)
  | a :: b :: rest => .ok (a.toNat * 256 + b.toNat, rest)
  | _ => .error "truncated"

def readText (limit : Nat) (bs : Bytes) : Except String (String × Bytes) := do
  let (n,rest) ← readWord bs
  if n > 16384 then throw "resource_limit"
  if rest.length < n then throw "truncated"
  let some s := String.fromUTF8? ⟨(rest.take n).toArray⟩ | throw "utf8"
  if s.length > limit then throw "resource_limit"
  return (s, rest.drop n)

def many {α : Type} (read : Bytes → Except String (α × Bytes)) :
    Nat → Bytes → Except String (List α × Bytes)
  | 0, bs => .ok ([],bs)
  | n+1, bs => do
    let (x,rest) ← read bs
    let (xs,tail) ← many read n rest
    return (x::xs,tail)

def readPair (read : Bytes → Except String (Tree × Bytes))
    (bs : Bytes) : Except String ((String × Tree) × Bytes) := do
  let (k,rest) ← readText 128 bs
  let (t,tail) ← read rest
  return ((k,t),tail)

def parse : Nat → Bytes → Except String (Tree × Bytes)
  | 0, _ => .error "resource_limit"
  | n+1, bs => do
    let tag :: rest := bs | throw "truncated"
    match tag.toNat with
    | 0 => return (.null, rest)
    | 1 => return (.bool false, rest)
    | 2 => return (.bool true, rest)
    | 3 =>
      let (s,tail) ← readText 6 rest
      return (.number s,tail)
    | 4 =>
      let (s,tail) ← readText 4096 rest
      return (.string s,tail)
    | 5 =>
      let (count,tail) ← readWord rest
      if count > 1024 then throw "resource_limit"
      let (ts,tail) ← many (parse n) count tail
      return (.array ts,tail)
    | 6 =>
      let (count,tail) ← readWord rest
      if count > 1024 then throw "resource_limit"
      let (fs,tail) ← many (readPair (parse n)) count tail
      return (.object fs,tail)
    | _ => throw "tag"

/-- Independent constructor serialization is checked against the exact input bytes.
Trailing bytes, noncanonical spelling or parser errors never become accepted. -/
def decode (fuel : Nat) (bs : Bytes) : Except String Tree := do
  if bs.length > 2 * 1024 * 1024 then throw "resource_limit"
  let (t,rest) ← parse fuel bs
  if !rest.isEmpty then throw "trailing"
  if bs == encode t then return t else throw "representation"

def Admissible : Nat → Tree → Prop
  | 0, _ => False
  | _+1, .null => True
  | _+1, .bool _ => True
  | _+1, .number s => s.length ≤ 6 ∧ (utf8 s).length ≤ 16384
  | _+1, .string s => s.length ≤ 4096 ∧ (utf8 s).length ≤ 16384
  | n+1, .array ts => ts.length ≤ 1024 ∧ ∀ t ∈ ts, Admissible n t
  | n+1, .object fs => fs.length ≤ 1024 ∧ ∀ p ∈ fs,
      p.1.length ≤ 128 ∧ (utf8 p.1).length ≤ 16384 ∧ Admissible n p.2

theorem readWord_complete (n : Nat) (h : n < 65536) (rest : Bytes) :
    readWord (word n ++ rest) = .ok (n,rest) := by
  simp only [word, List.cons_append, List.nil_append, readWord, UInt8.toNat_ofNat']
  have he : n / 256 % 256 * 256 + n % 256 = n := by omega
  simpa using congrArg (fun k => Except.ok (ε := String) (k, rest)) he

theorem utf8_roundtrip (s : String) : String.fromUTF8? ⟨(utf8 s).toArray⟩ = some s := by
  simp only [utf8, Array.toArray_toList, String.toUTF8_eq_toByteArray]
  simp only [String.fromUTF8?, dif_pos s.isValidUTF8, String.fromUTF8]

theorem readText_complete (s : String) (limit : Nat) (h : s.length ≤ limit)
    (hb : (utf8 s).length ≤ 16384) (rest : Bytes) :
    readText limit (text s ++ rest) = .ok (s,rest) := by
  simp only [text, List.append_assoc, readText, readWord_complete (utf8 s).length (by omega)]
  simp [bind, Except.bind, pure, Except.pure, Nat.not_lt.mpr hb,
    utf8_roundtrip, Nat.not_lt.mpr h]

theorem many_complete {α : Type} (write : α → Bytes)
    (read : Bytes → Except String (α × Bytes)) (xs : List α)
    (h : ∀ x ∈ xs, ∀ tail, read (write x ++ tail) = .ok (x, tail)) (rest : Bytes) :
    many read xs.length (xs.flatMap write ++ rest) = .ok (xs,rest) := by
  induction xs generalizing rest with
  | nil => rfl
  | cons x xs ih =>
    simp only [List.length_cons, List.flatMap_cons, List.append_assoc, many]
    rw [h x (by simp)]
    simp only [bind, Except.bind]
    rw [ih (by intro x hx; exact h x (by simp [hx]))]
    rfl

theorem parse_complete (fuel : Nat) (t : Tree) (h : Admissible fuel t) (rest : Bytes) :
    parse fuel (encode t ++ rest) = .ok (t,rest) := by
  induction fuel generalizing t rest with
  | zero => simp [Admissible] at h
  | succ n ih =>
    cases t with
    | null => simp [encode, parse, pure, Except.pure]
    | bool b => cases b <;> simp [encode, parse, pure, Except.pure]
    | number s =>
      simp [encode, parse, readText_complete s 6 h.1 h.2,
        bind, Except.bind, pure, Except.pure]
    | string s =>
      simp [encode, parse, readText_complete s 4096 h.1 h.2,
        bind, Except.bind, pure, Except.pure]
    | array ts =>
      have hw := readWord_complete ts.length (by have := h.1; omega)
      have hm := many_complete encode (parse n) ts (by intro x hx tail; exact ih x (h.2 x hx) tail)
      rw [encode]
      simp [parse, List.append_assoc, hw, hm, Nat.not_lt.mpr h.1,
        bind, Except.bind, pure, Except.pure]
    | object fs =>
      have hw := readWord_complete fs.length (by have := h.1; omega)
      have hp : ∀ p ∈ fs, ∀ tail,
          readPair (parse n) ((text p.1 ++ encode p.2) ++ tail) = .ok (p,tail) := by
        intro p hp tail
        have hh := h.2 p hp
        simp [readPair, List.append_assoc, readText_complete p.1 128 hh.1 hh.2.1,
          ih p.2 hh.2.2, bind, Except.bind, pure, Except.pure]
      have hm : ∀ tail, many (readPair (parse n)) fs.length
          (fs.flatMap (fun p => text p.1 ++ encode p.2) ++ tail) = .ok (fs,tail) :=
        many_complete (α := String × Tree) (fun p => text p.1 ++ encode p.2)
          (readPair (parse n)) fs hp
      rw [encode]
      simp [parse, List.append_assoc, hw, hm, Nat.not_lt.mpr h.1,
        bind, Except.bind, pure, Except.pure]

theorem decode_sound (fuel : Nat) (bs : Bytes) (t : Tree) (h : decode fuel bs = .ok t) :
    bs = encode t := by
  unfold decode at h
  split at h
  · simp [bind, Except.bind, throw] at h
  · cases hp : parse fuel bs with
    | error e => simp [hp, bind, Except.bind] at h
    | ok v =>
      simp only [hp, bind, Except.bind] at h
      split at h
      · simp [throw] at h
      · split at h
        · rename_i he
          simp only [pure, Except.pure, Except.ok.injEq] at h
          exact h ▸ (by simpa using he)
        · simp [throw] at h

theorem decode_complete (fuel : Nat) (t : Tree) (h : Admissible fuel t)
    (hb : (encode t).length ≤ 2 * 1024 * 1024) : decode fuel (encode t) = .ok t := by
  have hp := parse_complete fuel t h []
  simp only [List.append_nil] at hp
  simp [decode, Nat.not_lt.mpr hb, hp, bind, Except.bind, pure, Except.pure]

theorem encode_injective_on (fuel : Nat) (t u : Tree)
    (ht : Admissible fuel t) (hu : Admissible fuel u) (he : encode t = encode u) : t = u := by
  have a := parse_complete fuel t ht []
  have b := parse_complete fuel u hu []
  rw [he] at a
  have hh := Except.ok.inj (a.symm.trans b)
  exact congrArg Prod.fst hh

def magic : Bytes := [83, 81, 76, 66, 84, 1]
def packet (t : Tree) : Bytes := magic ++ encode t

def decodePacket (fuel : Nat) (bs : Bytes) : Except String Tree :=
  if bs.length > 2 * 1024 * 1024 then .error "resource_limit"
  else if bs.take 6 = magic then decode fuel (bs.drop 6) else .error "version"

theorem packet_sound (fuel : Nat) (bs : Bytes) (t : Tree)
    (h : decodePacket fuel bs = .ok t) : bs = packet t := by
  unfold decodePacket at h
  split at h
  · contradiction
  · split at h
    · rename_i hm
      have hd := decode_sound fuel (bs.drop 6) t h
      calc
        bs = bs.take 6 ++ bs.drop 6 := (List.take_append_drop 6 bs).symm
        _ = packet t := by rw [hm, hd]; rfl
    · contradiction

theorem packet_complete (fuel : Nat) (t : Tree) (ha : Admissible fuel t)
    (hb : (packet t).length ≤ 2 * 1024 * 1024) : decodePacket fuel (packet t) = .ok t := by
  have he : (encode t).length ≤ 2 * 1024 * 1024 := by
    simp only [packet, List.length_append] at hb
    omega
  unfold decodePacket
  rw [if_neg (Nat.not_lt.mpr hb)]
  simp [packet, magic, decode_complete fuel t ha he]

theorem preserves_tree (fuel : Nat) (source actual : Tree)
    (ha : Admissible fuel source) (hb : (packet source).length ≤ 2 * 1024 * 1024)
    (h : decodePacket fuel (packet source) = .ok actual) : actual = source :=
  Except.ok.inj (h.symm.trans (packet_complete fuel source ha hb))

theorem preserves_fields (fuel : Nat) (source actual : Tree) (name : String)
    (ha : Admissible fuel source) (hb : (packet source).length ≤ 2 * 1024 * 1024)
    (h : decodePacket fuel (packet source) = .ok actual) :
    field actual name = field source name ∧ decodeAST actual = decodeAST source := by
  rw [preserves_tree fuel source actual ha hb h]
  exact ⟨rfl,rfl⟩

/-- Exact byte-array data is used once, without a String/JSON conversion. -/
def decodeByteArray (fuel : Nat) (bs : ByteArray) : Except String Tree :=
  decodePacket fuel bs.data.toList

def acceptBytes (fuel : Nat) (e : ExpectedInstance) (bs : ByteArray)
    (p : ParsedBoundCertificate) : Bool :=
  match decodeByteArray fuel bs with
  | .error _ => false
  | .ok t => acceptDecoded e t p

theorem accepted_bytes_rounding (fuel : Nat) (e : ExpectedInstance) (bs : ByteArray)
    (p : ParsedBoundCertificate) (h : acceptBytes fuel e bs p = true) :
    ∃ t, bs.data.toList = packet t ∧ decodeAST t = some e.input ∧ ASTRep t e.input ∧
      NumericRealRounding.realRound NumericRoundingCertificates.binary64 e.input.gap
        = p.result := by
  unfold acceptBytes at h
  cases hd : decodeByteArray fuel bs with
  | error err => simp [hd] at h
  | ok t =>
    simp only [hd] at h
    have hr := accepted_decoded_rounding e t p h
    exact ⟨t, packet_sound fuel bs.data.toList t hd, hr.1,
      decodeAST_sound t e.input hr.1, hr.2⟩

theorem mismatch_rejected (fuel : Nat) (e : ExpectedInstance) (bs : ByteArray)
    (t : Tree) (x : SQLInstance) (p : ParsedBoundCertificate)
    (ht : decodeByteArray fuel bs = .ok t) (hx : decodeAST t = some x)
    (hne : x ≠ e.input) : acceptBytes fuel e bs p = false := by
  simp only [acceptBytes, ht]
  exact decoded_mismatch_rejected e t p x hx hne

structure NumericSQLByteTransportSuite : Prop where
  sound : ∀ fuel bs t, decodePacket fuel bs = .ok t → bs = packet t
  complete : ∀ fuel t, Admissible fuel t → (packet t).length ≤ 2 * 1024 * 1024 →
    decodePacket fuel (packet t) = .ok t
  rounding : ∀ fuel e bs p, acceptBytes fuel e bs p = true →
    ∃ t, bs.data.toList = packet t ∧ decodeAST t = some e.input ∧ ASTRep t e.input ∧
      NumericRealRounding.realRound NumericRoundingCertificates.binary64 e.input.gap = p.result

theorem numeric_sql_byte_transport_master_suite : NumericSQLByteTransportSuite := {
  sound := packet_sound
  complete := packet_complete
  rounding := accepted_bytes_rounding
}

end NumericSQLByteTransport

/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLInstanceDecoder
import Lean.Data.Json.FromToJson.Basic

/-! Tagged JSON AST transport. The theorem starts at Lean.Json, not UTF-8 bytes.
The representation specification is a constructor encoding independent of decoding.
Object order and duplicate keys are preserved as lists, never Json objects. -/
namespace NumericSQLASTTransport
open Lean NumericSQLInstanceDecoder NumericSQLExpectedInstance

/-- Declarative tagged representation; it performs no parsing or validation. -/
def encode : Tree → Json
  | .null => .arr #[.str "null"]
  | .bool b => .arr #[.str "bool", .bool b]
  | .number s => .arr #[.str "number", .str s]
  | .string s => .arr #[.str "string", .str s]
  | .array ts => .arr #[.str "array", .arr (ts.map encode).toArray]
  | .object fs => .arr #[.str "object", .arr (fs.map fun p =>
      Json.arr #[.str p.1, encode p.2]).toArray]
termination_by t => sizeOf t
decreasing_by
  all_goals simp_wf
  · decreasing_trivial
  · have h := List.sizeOf_lt_of_mem ‹_ ∈ _›
    cases p
    simp_all only [Prod.mk.sizeOf_spec]
    omega

private theorem array_eq {a : Array Json} {xs : List Json} (h : a.toList = xs) :
    a = xs.toArray := by rw [← h]

/-- Successful list traversal preserves every element and its position. -/
def sequence {α β : Type} (enc : β → α)
    (f : (a : α) → Except String {b : β // a = enc b}) :
    (xs : List α) → Except String {ys : List β // xs = ys.map enc}
  | [] => .ok ⟨[], rfl⟩
  | x :: xs => do
    let y ← f x
    let ys ← sequence enc f xs
    return ⟨y.val :: ys.val, by simp [y.property, ys.property]⟩

def encodePair (p : String × Tree) : Json := .arr #[.str p.1, encode p.2]

def decodeField (f : (j : Json) → Except String {t : Tree // j = encode t})
    (p : Json) : Except String {q : String × Tree // p = encodePair q} := do
  match hp : p with
  | .arr pair =>
    match hh : pair.toList with
    | [.str k, v] =>
      if k.length > 128 then throw "resource_limit"
      let t ← f v
      return ⟨(k,t.val), by simp [encodePair, hp, array_eq hh, ← t.property]⟩
    | _ => throw "pair"
  | _ => throw "pair"

/-- Actual executable decoder, returning an erased proof of exact representation.
Budgets agree with transport 1.0.1: depth fuel, 1024 children, 128 key chars,
4096 string chars, 6 number-token chars. No number-token is parsed here. -/
def decodeCertified : (fuel : Nat) → (j : Json) →
    Except String {t : Tree // j = encode t}
  | 0, _ => .error "resource_limit"
  | fuel + 1, j => do
    match hj : j with
    | .arr a =>
      match ha : a.toList with
      | [.str "null"] =>
        return ⟨.null, by simp [encode, hj, array_eq ha]⟩
      | [.str "bool", .bool b] =>
        return ⟨.bool b, by simp [encode, hj, array_eq ha]⟩
      | [.str "number", .str s] =>
        if s.length > 6 then throw "resource_limit"
        return ⟨.number s, by simp [encode, hj, array_eq ha]⟩
      | [.str "string", .str s] =>
        if s.length > 4096 then throw "resource_limit"
        return ⟨.string s, by simp [encode, hj, array_eq ha]⟩
      | [.str "array", .arr xs] =>
        if xs.size > 1024 then throw "resource_limit"
        let ts ← sequence encode (decodeCertified fuel) xs.toList
        return ⟨.array ts.val, by
          simp [encode, hj, array_eq ha, ← ts.property]⟩
      | [.str "object", .arr xs] =>
        if xs.size > 1024 then throw "resource_limit"
        let fs ← sequence encodePair (decodeField (decodeCertified fuel)) xs.toList
        return ⟨.object fs.val, by
          rw [hj, array_eq ha, encode]
          change Json.arr #[.str "object", .arr xs] =
            Json.arr #[.str "object", .arr (fs.val.map encodePair).toArray]
          exact congrArg (fun a => Json.arr #[.str "object", Json.arr a])
            (congrArg List.toArray fs.property)⟩
      | _ => throw "tag_or_arity"
    | _ => throw "tag_or_arity"

def fromTransport (fuel : Nat) (j : Json) : Except String Tree :=
  (decodeCertified fuel j).map Subtype.val

theorem fromTransport_sound (fuel : Nat) (j : Json) (t : Tree)
    (h : fromTransport fuel j = .ok t) : j = encode t := by
  unfold fromTransport at h
  cases hd : decodeCertified fuel j with
  | error e => simp [hd, Except.map] at h
  | ok v =>
    simp only [hd, Except.map, Except.ok.injEq] at h
    exact h ▸ v.property

theorem encode_injective : Function.Injective encode := by
  intro t u h
  have main : ∀ t u, encode t = encode u → t = u := by
    apply Tree.rec
      (motive_1 := fun t => ∀ u, encode t = encode u → t = u)
      (motive_2 := fun xs => ∀ ys, xs.map encode = ys.map encode → xs = ys)
      (motive_3 := fun fs => ∀ gs,
        fs.map (fun p => Json.arr #[.str p.1, encode p.2]) =
        gs.map (fun p => Json.arr #[.str p.1, encode p.2]) → fs = gs)
      (motive_4 := fun p => ∀ q : String × Tree,
        Json.arr #[.str p.1, encode p.2] = Json.arr #[.str q.1, encode q.2] → p = q)
    · intro u h; cases u <;> simp_all [encode]
    · intro b u h; cases u <;> simp_all [encode]
    · intro s u h; cases u <;> simp_all [encode]
    · intro s u h; cases u <;> simp_all [encode]
    · intro xs ih u h; cases u <;> simp only [encode, Json.arr.injEq,
        Array.mk.injEq, List.cons.injEq] at h
      all_goals first | contradiction | (simp_all <;> aesop)
    · intro fs ih u h; cases u <;> simp only [encode, Json.arr.injEq,
        Array.mk.injEq, List.cons.injEq] at h
      all_goals first | contradiction | (simp_all <;> aesop)
    · intro ys h; cases ys <;> simp_all
    · intro x xs ih iht ys h; cases ys <;> simp_all; aesop
    · intro ys h; cases ys <;> simp_all
    · intro x xs ih iht ys h; cases ys <;> simp_all; aesop
    · intro k t ih q h; cases q; simp_all; aesop
  exact main t u h

/-- Independent finite resource domain, not a test of decoder success. -/
def Admissible : Nat → Tree → Prop
  | 0, _ => False
  | _+1, .null => True
  | _+1, .bool _ => True
  | _+1, .number s => s.length ≤ 6
  | _+1, .string s => s.length ≤ 4096
  | n+1, .array ts => ts.length ≤ 1024 ∧ ∀ t ∈ ts, Admissible n t
  | n+1, .object fs => fs.length ≤ 1024 ∧ ∀ p ∈ fs, p.1.length ≤ 128 ∧ Admissible n p.2

private theorem sequence_complete {α β : Type} (enc : β → α)
    (f : (a : α) → Except String {b : β // a = enc b}) (xs : List α)
    (h : ∀ x ∈ xs, ∃ v, f x = .ok v) : ∃ vs, sequence enc f xs = .ok vs := by
  induction xs with
  | nil => simp [sequence]
  | cons x xs ih =>
    obtain ⟨v,hv⟩ := h x (by simp)
    obtain ⟨vs,hvs⟩ := ih (by intro x hx; exact h x (by simp [hx]))
    simp [sequence, hv, hvs, bind, Except.bind, pure, Except.pure]

def Succeeds {α : Type} : Except String α → Prop
  | .ok _ => True
  | .error _ => False

theorem fromTransport_succeeds (fuel : Nat) (t : Tree) (h : Admissible fuel t) :
    Succeeds (fromTransport fuel (encode t)) := by
  induction fuel generalizing t with
  | zero => simp [Admissible] at h
  | succ n ih =>
    cases t with
    | null =>
      rw [encode]
      simp [fromTransport, decodeCertified, Succeeds, Except.map, pure, Except.pure]
    | bool b =>
      rw [encode]
      simp [fromTransport, decodeCertified, Succeeds, Except.map, pure, Except.pure]
    | number s =>
      rw [encode]
      simp [fromTransport, decodeCertified, Succeeds, Except.map, pure, Except.pure,
        show ¬s.length > 6 from Nat.not_lt.mpr h]
    | string s =>
      rw [encode]
      simp [fromTransport, decodeCertified, Succeeds, Except.map, pure, Except.pure,
        show ¬s.length > 4096 from Nat.not_lt.mpr h]
    | array ts =>
      have hs : ∀ j ∈ ts.map encode, ∃ v, decodeCertified n j = .ok v := by
        intro j hj
        obtain ⟨x,hx,rfl⟩ := List.mem_map.mp hj
        have hx := ih x (h.2 x hx)
        cases hd : decodeCertified n (encode x) with
        | error e => simp [fromTransport, hd, Succeeds, Except.map] at hx
        | ok v => exact ⟨v,rfl⟩
      obtain ⟨v,hv⟩ := sequence_complete encode (decodeCertified n) (ts.map encode) hs
      rw [encode]
      simp [fromTransport, decodeCertified, Succeeds, Except.map, bind, Except.bind,
        pure, Except.pure,
        show ¬ts.length > 1024 from Nat.not_lt.mpr h.1, hv]
    | object fs =>
      have hs : ∀ j ∈ fs.map encodePair,
          ∃ v, decodeField (decodeCertified n) j = .ok v := by
        intro j hj
        obtain ⟨⟨k,t⟩,ht,rfl⟩ := List.mem_map.mp hj
        have hh := h.2 (k,t) ht
        have hx := ih t hh.2
        cases hd : decodeCertified n (encode t) with
        | error e => simp [fromTransport, hd, Succeeds, Except.map] at hx
        | ok v =>
          simp [decodeField, encodePair, hd, show ¬k.length > 128 from Nat.not_lt.mpr hh.1,
            bind, Except.bind, pure, Except.pure]
      obtain ⟨v,hv⟩ := sequence_complete encodePair (decodeField (decodeCertified n))
        (fs.map encodePair) hs
      rw [encode]
      change Succeeds (fromTransport (n+1)
        (.arr #[.str "object", .arr (fs.map encodePair).toArray]))
      simp [fromTransport, decodeCertified, Succeeds, Except.map,
        show ¬fs.length > 1024 from Nat.not_lt.mpr h.1, hv,
        bind, Except.bind, pure, Except.pure]

theorem fromTransport_complete (fuel : Nat) (t : Tree) (h : Admissible fuel t) :
    fromTransport fuel (encode t) = .ok t := by
  have hs := fromTransport_succeeds fuel t h
  cases hd : fromTransport fuel (encode t) with
  | error e => simp [hd, Succeeds] at hs
  | ok u =>
    have he := encode_injective (fromTransport_sound fuel (encode t) u hd)
    simp [he]

/-- The entire tree, not only its SQL numeric projection, is preserved. -/
theorem preserves_tree (fuel : Nat) (source actual : Tree)
    (h : fromTransport fuel (encode source) = .ok actual) : actual = source :=
  (encode_injective (fromTransport_sound fuel (encode source) actual h)).symm

theorem preserves_field (fuel : Nat) (source actual : Tree) (name : String)
    (h : fromTransport fuel (encode source) = .ok actual) :
    field actual name = field source name := by rw [preserves_tree fuel source actual h]

theorem preserves_SQLInstance (fuel : Nat) (source actual : Tree)
    (h : fromTransport fuel (encode source) = .ok actual) :
    decodeAST actual = decodeAST source := by rw [preserves_tree fuel source actual h]

/-- Both transport and AST acceptance must succeed; no fallback. -/
def acceptTransport (fuel : Nat) (e : ExpectedInstance) (j : Json)
    (p : ParsedBoundCertificate) : Bool :=
  match fromTransport fuel j with
  | .error _ => false
  | .ok t => acceptDecoded e t p

theorem accepted_transport_rounding (fuel : Nat) (e : ExpectedInstance) (j : Json)
    (p : ParsedBoundCertificate) (h : acceptTransport fuel e j p = true) :
    ∃ t, j = encode t ∧ decodeAST t = some e.input ∧ ASTRep t e.input ∧
      NumericRealRounding.realRound NumericRoundingCertificates.binary64 e.input.gap
        = p.result := by
  unfold acceptTransport at h
  cases hd : fromTransport fuel j with
  | error err => simp [hd] at h
  | ok t =>
    simp only [hd] at h
    have hr := accepted_decoded_rounding e t p h
    exact ⟨t, fromTransport_sound fuel j t hd, hr.1,
      decodeAST_sound t e.input hr.1, hr.2⟩

theorem transport_mismatch_rejected (fuel : Nat) (e : ExpectedInstance)
    (source actual : Tree) (x : SQLInstance) (p : ParsedBoundCertificate)
    (ht : fromTransport fuel (encode source) = .ok actual)
    (hx : decodeAST source = some x) (hne : x ≠ e.input) :
    acceptTransport fuel e (encode source) p = false := by
  simp only [acceptTransport, ht]
  rw [preserves_tree fuel source actual ht]
  exact decoded_mismatch_rejected e source p x hx hne

structure NumericSQLASTTransportSuite : Prop where
  sound : ∀ fuel j t, fromTransport fuel j = .ok t → j = encode t
  complete : ∀ fuel t, Admissible fuel t → fromTransport fuel (encode t) = .ok t
  injective : Function.Injective encode
  preserves : ∀ fuel source actual,
    fromTransport fuel (encode source) = .ok actual → actual = source

theorem numeric_sql_ast_transport_master_suite : NumericSQLASTTransportSuite := {
  sound := fromTransport_sound
  complete := fromTransport_complete
  injective := encode_injective
  preserves := preserves_tree
}

end NumericSQLASTTransport

/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLByteTransport

/-! Independent concrete grammar for the integer-only external SQL JSON profile.
The grammar, rendering and denotation do not invoke the parser. -/
namespace NumericSQLJSONGrammar
open NumericSQLInstanceDecoder
abbrev Chars := List Char

def space (c : Char) : Bool := [' ', '\t', '\n', '\r'].contains c
def Spaces (cs : Chars) : Prop := ∀ c ∈ cs, space c = true
instance (cs : Chars) : Decidable (Spaces cs) := inferInstanceAs (Decidable (∀ c ∈ cs, _))
def digit (c : Char) : Bool := '0' ≤ c && c ≤ '9'
def hexDigit (c : Char) : Bool := digit c || ('a' ≤ c && c ≤ 'f') || ('A' ≤ c && c ≤ 'F')
def hexValue (c : Char) : Nat :=
  if c ≤ '9' then c.toNat - 48 else if c ≤ 'F' then c.toNat - 55 else c.toNat - 87
def hex (cs : Chars) : Nat := cs.foldl (fun n c => 16*n + hexValue c) 0
def Hex4 (cs : Chars) : Prop := cs.length = 4 ∧ ∀ c ∈ cs, hexDigit c = true
instance (cs : Chars) : Decidable (Hex4 cs) := inferInstanceAs (Decidable (_ ∧ _))
def scalar (n : Nat) : Prop := n < 0x110000 ∧ (n < 0xD800 ∨ 0xDFFF < n)
instance (n : Nat) : Decidable (scalar n) := inferInstanceAs (Decidable (_ ∧ _))

inductive JUnit where
  | literal (c : Char)
  | escaped (c : Char)
  | unicode (hs : Chars)
  | pair (hi lo : Chars)

def JUnit.raw : JUnit → Chars
  | .literal c => [c]
  | .escaped c => ['\\',c]
  | .unicode hs => ['\\','u'] ++ hs
  | .pair hi lo => ['\\','u'] ++ hi ++ ['\\','u'] ++ lo

def JUnit.value : JUnit → Char
  | .literal c => c
  | .escaped c => match c with
    | 'b' => '\x08' | 'f' => '\x0c' | 'n' => '\n' | 'r' => '\r' | 't' => '\t' | _ => c
  | .unicode hs => Char.ofNat (hex hs)
  | .pair hi lo => Char.ofNat (0x10000 + (hex hi - 0xD800)*1024 + (hex lo - 0xDC00))

def JUnit.Valid : JUnit → Prop
  | .literal c => 32 ≤ c.toNat ∧ c ≠ '"' ∧ c ≠ '\\'
  | .escaped c => c ∈ ['"','\\','/','b','f','n','r','t']
  | .unicode hs => Hex4 hs ∧ scalar (hex hs)
  | .pair hi lo => Hex4 hi ∧ Hex4 lo ∧ 0xD800 ≤ hex hi ∧ hex hi ≤ 0xDBFF ∧
      0xDC00 ≤ hex lo ∧ hex lo ≤ 0xDFFF
instance (u : JUnit) : Decidable u.Valid := by cases u <;> unfold JUnit.Valid <;> infer_instance

def stringRaw (us : List JUnit) : Chars := ['"'] ++ us.flatMap JUnit.raw ++ ['"']
def stringValue (us : List JUnit) : String := String.ofList (us.map JUnit.value)
def GoodString (us : List JUnit) : Prop := ∀ u ∈ us, u.Valid
instance (us : List JUnit) : Decidable (GoodString us) := inferInstanceAs (Decidable (∀ u ∈ us, _))

def magnitude : Chars → Prop
  | ['0'] => True
  | c::cs => '1' ≤ c ∧ c ≤ '9' ∧ ∀ d ∈ cs, digit d = true
  | _ => False
instance (cs : Chars) : Decidable (magnitude cs) := by
  unfold magnitude
  split <;> infer_instance

def IntegerToken (cs : Chars) : Prop :=
  match cs with | '-'::rest => magnitude rest | _ => magnitude cs
instance (cs : Chars) : Decidable (IntegerToken cs) := by
  unfold IntegerToken
  split <;> infer_instance

def integerValue (cs : Chars) : String := if cs == ['-','0'] then "0" else String.ofList cs

inductive Syntax where
  | null
  | bool (b : Bool)
  | number (raw : Chars)
  | string (us : List JUnit)
  | array (lead : Chars) (children : List Syntax)
  | object (lead : Chars) (fields : List (Chars × List JUnit × Chars × Syntax))
  | pad (left : Chars) (s : Syntax) (right : Chars)

def commaJoin (ss : List Chars) : Chars := (List.intersperse [','] ss).flatten

def render : Syntax → Chars
  | .null => "null".toList
  | .bool b => (if b then "true" else "false").toList
  | .number cs => cs
  | .string us => stringRaw us
  | .array ws xs => ['['] ++ ws ++ commaJoin (xs.map render) ++ [']']
  | .object ws fs => ['{'] ++ ws ++ commaJoin (fs.map fun p =>
      p.1 ++ stringRaw p.2.1 ++ p.2.2.1 ++ [':'] ++ render p.2.2.2) ++ ['}']
  | .pad l s r => l ++ render s ++ r
termination_by s => sizeOf s
decreasing_by
  all_goals simp_wf
  · decreasing_trivial
  · have h := List.sizeOf_lt_of_mem ‹_ ∈ _›
    rcases p with ⟨l,u,r,s⟩
    simp_all only [Prod.mk.sizeOf_spec]
    omega
  · omega

def denote : Syntax → Tree
  | .null => .null
  | .bool b => .bool b
  | .number cs => .number (integerValue cs)
  | .string us => .string (stringValue us)
  | .array _ xs => .array (xs.map denote)
  | .object _ fs => .object (fs.map fun p => (stringValue p.2.1,denote p.2.2.2))
  | .pad _ s _ => denote s
termination_by s => sizeOf s
decreasing_by
  all_goals simp_wf
  · decreasing_trivial
  · have h := List.sizeOf_lt_of_mem ‹_ ∈ _›
    rcases p with ⟨l,u,r,s⟩
    simp_all only [Prod.mk.sizeOf_spec]
    omega
  · omega

/-- Declarative grammar/domain constraints, independent of parser and validity checker. -/
def Good : Nat → Syntax → Prop
  | 0, _ => False
  | _+1, .null => True
  | _+1, .bool _ => True
  | _+1, .number cs => IntegerToken cs ∧ cs.length ≤ 6
  | _+1, .string us => GoodString us ∧ us.length ≤ 4096
  | n+1, .array ws xs => Spaces ws ∧ xs.length ≤ 1024 ∧ ∀ x ∈ xs, Good n x
  | n+1, .object ws fs => Spaces ws ∧ fs.length ≤ 1024 ∧
      (fs.map fun p => stringValue p.2.1).Nodup ∧ ∀ p ∈ fs,
      Spaces p.1 ∧ GoodString p.2.1 ∧ p.2.1.length ≤ 128 ∧ Spaces p.2.2.1 ∧ Good n p.2.2.2
  | n+1, .pad l s r => Spaces l ∧ Good n s ∧ Spaces r

def check : Nat → Syntax → Bool
  | 0, _ => false
  | _+1, .null => true
  | _+1, .bool _ => true
  | _+1, .number cs => decide (IntegerToken cs) && decide (cs.length ≤ 6)
  | _+1, .string us => decide (GoodString us) && decide (us.length ≤ 4096)
  | n+1, .array ws xs => ws.all space && decide (xs.length ≤ 1024) && xs.all (check n)
  | n+1, .object ws fs => ws.all space && decide (fs.length ≤ 1024) &&
      decide ((fs.map fun p => stringValue p.2.1).Nodup) && fs.all (fun p =>
      p.1.all space && decide (GoodString p.2.1) && decide (p.2.1.length ≤ 128) &&
      p.2.2.1.all space && check n p.2.2.2)
  | n+1, .pad l s r => l.all space && check n s && r.all space

theorem check_iff (fuel : Nat) (s : Syntax) : check fuel s = true ↔ Good fuel s := by
  induction fuel generalizing s with
  | zero => simp [check, Good]
  | succ n ih =>
    cases s <;> simp [check, Good, Spaces, Bool.and_eq_true, List.all_eq_true, ih, and_assoc]

/-- A declarative grammar representation: no mention of decoding success. -/
def Represents (fuel : Nat) (bs : List UInt8) (t : Tree) : Prop :=
  ∃ s, Good fuel s ∧ bs = (String.ofList (render s)).toUTF8.data.toList ∧ denote s = t

/-- Every proposed parse is checked against grammar and the *original* source bytes. -/
def certify (fuel : Nat) (bs : List UInt8) (s : Syntax) : Option Tree :=
  if check fuel s && (bs == (String.ofList (render s)).toUTF8.data.toList)
    then some (denote s) else none

theorem certify_sound (fuel : Nat) (bs : List UInt8) (s : Syntax) (t : Tree)
    (h : certify fuel bs s = some t) : Represents fuel bs t := by
  unfold certify at h
  split at h
  · rename_i hc
    have hg : check fuel s = true ∧
        (bs == (String.ofList (render s)).toUTF8.data.toList) = true := by
      simpa only [Bool.and_eq_true] using hc
    have he : bs = (String.ofList (render s)).toUTF8.data.toList := by simpa using hg.2
    exact ⟨s,(check_iff _ _).mp hg.1,he,Option.some.inj h⟩
  · contradiction

theorem certify_complete (fuel : Nat) (s : Syntax) (hg : Good fuel s) :
    certify fuel (String.ofList (render s)).toUTF8.data.toList s = some (denote s) := by
  simp [certify, (check_iff _ _).mpr hg]

end NumericSQLJSONGrammar

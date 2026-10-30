#!/usr/bin/env python3
"""Bounded index of exact string fields. Content stays in the original context."""
import argparse
import json
from pathlib import Path
import sys

import knowledge as k

MAX_CARDS = 32
MAX_FIELDS = 4096
MAX_NODES = 32768
MAX_POINTER = 512


def string_fields(card):
    k.require(type(card) is dict, 'invalid_input:card_object')
    paths=[]; visited=0
    def walk(value, pointer, depth):
        nonlocal visited
        visited+=1
        k.require(visited<=MAX_NODES and depth<=k.MAX_DEPTH, 'resource_limit:field_tree')
        k.require(len(pointer)<=MAX_POINTER, 'resource_limit:pointer_length')
        if type(value) is str:
            if value:
                paths.append(pointer)
                k.require(len(paths)<=MAX_FIELDS, 'resource_limit:field_count')
        elif type(value) is dict:
            k.require(all(type(key) is str for key in value), 'invalid_input:field_key')
            for key in sorted(value):
                token=key.replace('~','~0').replace('/','~1')
                walk(value[key],pointer+'/'+token,depth+1)
        elif type(value) is list:
            for i,item in enumerate(value):walk(item,pointer+'/'+str(i),depth+1)
        else:
            k.require(value is None or type(value) in (bool,int), 'invalid_input:field_value')
    walk(card,'',0)
    return paths


def make_index(context):
    k.require(type(context) is dict and context.get('schema')=='geek-work-memory-context-1',
              'invalid_input:context_schema')
    k.require(context.get('disposition')=='context_ready', 'invalid_witness:context_not_ready')
    rows=context.get('cards')
    k.require(type(rows) is list and 0<len(rows)<=MAX_CARDS, 'resource_limit:index_cards')
    cards=[];seen=set();total=0
    for row in rows:
        k.require(type(row) is dict and type(row.get('card')) is dict, 'invalid_input:context_card')
        card=row['card'];k.card(card)
        k.require(card['id'] not in seen, 'invalid_input:duplicate_card')
        seen.add(card['id']);paths=string_fields(card);total+=len(paths)
        k.require(total<=MAX_FIELDS, 'resource_limit:field_count')
        cards.append(dict(card_id=card['id'],revision=card['revision'],
                          card_sha256=k.digest(k.canonical(card)),string_fields=paths))
    return dict(schema='geek-work-field-index-1',context_sha256=k.digest(k.canonical(context)),
                cards=sorted(cards,key=lambda c:c['card_id']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('context',type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    try:
        index=make_index(k.load(args.context));k.write_new(args.output,k.canonical(index)+b'\n')
        return 0
    except (k.Refusal,OSError,UnicodeError,ValueError) as exc:
        print(json.dumps(dict(status='rejected',reason=str(exc))),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())

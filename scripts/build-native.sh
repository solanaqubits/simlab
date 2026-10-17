#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p .lake
cc -c simulations/decoder_audit/runtime/stack_init.c -o .lake/decoder_stack_init.o
lake build --wfail sql_stream_reader sql_stream_probe sql_session_binding sql_control_decoder sql_decision_envelope sql_certificate_decoder sql_instance_json_decoder sql_json_parser_probe sql_instance_byte_decoder sql_byte_transport_probe sql_instance_decoder sql_ast_transport_probe

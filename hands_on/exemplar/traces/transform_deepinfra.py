import csv
import ast
import json

input_file = "/home/aflowers/Documents/dynamo_exemplar/traces/deepInfra_deepseek_requests_july13-14_24hr.csv"
output_file = "deepinfra_block_parse_output.jsonl"
BLOCK_SIZE = 32


all_data = []
counter = 0
reverse_block_counter = -1
reset_hashes = {}
with open(input_file, 'r', encoding='utf-8') as file:
    reader = csv.DictReader(file)
    for row_idx, row in enumerate(reader):
        timestamp = row['timestamp']
        model_name = row['model_name']
        in_tokens = int(row['in_tokens'])
        out_tokens = int(row['out_tokens'])
        duration_ms = int(row['duration_ms'])
        try:
            block_hashes = ast.literal_eval(row['block_hashes'])
        except (SyntaxError, ValueError) as exc:
            print(f"Skipping row {row_idx}: failed to parse block_hashes ({exc})")
            continue
        breakpoint_block_index = in_tokens // BLOCK_SIZE
        tokens_in_breakpoint_block = in_tokens % BLOCK_SIZE
        input_hashes = block_hashes[:breakpoint_block_index]
        if row_idx % 100_000 == 0:
            print(row_idx, len(block_hashes), in_tokens, breakpoint_block_index, tokens_in_breakpoint_block)
        if tokens_in_breakpoint_block != 0:
            input_hashes.append(reverse_block_counter)
            reverse_block_counter -= 1
        new_input_hashes = []
        for ii in input_hashes:
            if ii not in reset_hashes:
                reset_hashes[ii] = counter
                counter += 1
            new_input_hashes.append(reset_hashes[ii])
        input_hashes = new_input_hashes
            
        #input_hashes.append(float(f"{block_hashes[breakpoint_block_index]}.{tokens_in_breakpoint_block}"))
        output_hashes = block_hashes[breakpoint_block_index+1:]

        result = {
            "request_id": row_idx + 1,
            "timestamp": int(timestamp)/1_000_000,
            "model_name": model_name,
            "input_length": in_tokens,
            "output_length": out_tokens,
            "duration_ms": duration_ms,
            # "original_block_hashes": block_hashes,
            "hash_ids": input_hashes,
            # "output_hashes": output_hashes,
        }
        all_data.append(result)

min_timestamp = min(data['timestamp'] for data in all_data)

print(f"Writing data to : {output_file}")

with open(output_file, 'w', encoding='utf-8') as file:
    for data in all_data:
        data['timestamp'] = data['timestamp'] - min_timestamp
        file.write(json.dumps(data) + '\n')
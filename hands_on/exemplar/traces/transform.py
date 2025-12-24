from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import os

import orjson


def chunked_iterable(iterable, size):
    iterator = iter(iterable)
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            break
        yield chunk


def process_chunk(chunk, start_ms, end_ms, scale, max_isl):
    processed = 0
    kept = []
    for line in chunk:
        processed += 1
        data = orjson.loads(line)

        timestamp = data["timestamp"]
        if timestamp < start_ms:
            continue
        if end_ms is not None and timestamp >= end_ms:
            continue
        if max_isl is not None and data["input_length"] > max_isl:
            continue

        data["timestamp"] = int((timestamp - start_ms) * scale)
        kept.append(orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE))

    return processed, kept


def main():
    parser = ArgumentParser()
    parser.add_argument("file", type=str)
    parser.add_argument("output_file", type=str)
    parser.add_argument("--start-s", type=int, default=0)
    parser.add_argument("--end-s", type=int, default=None)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--max-isl", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--log-every", type=int, default=100000)
    args = parser.parse_args()

    start_ms = args.start_s * 1000
    end_ms = args.end_s * 1000 if args.end_s is not None else None

    if end_ms is not None and end_ms < start_ms:
        raise ValueError("End time is before start time")
    if args.chunk_size <= 0:
        raise ValueError("chunk-size must be positive")
    if args.workers is not None and args.workers <= 0:
        raise ValueError("workers must be positive when provided")
    if args.log_every <= 0:
        raise ValueError("log-every must be positive")

    workers = args.workers or os.cpu_count() or 1

    total_processed = 0
    total_kept = 0
    next_log = args.log_every

    with open(args.file, "r", encoding="utf-8") as input_file, open(
        args.output_file, "wb"
    ) as output_file:
        def submit_chunk(executor, chunk):
            return executor.submit(
                process_chunk, chunk, start_ms, end_ms, args.scale, args.max_isl
            )

        def drain_result(result):
            nonlocal total_processed, total_kept, next_log
            processed, kept = result
            total_processed += processed
            total_kept += len(kept)

            for item in kept:
                output_file.write(item)

            while total_processed >= next_log:
                print(
                    f"Processed {total_processed:,} lines (kept {total_kept:,})."
                )
                next_log += args.log_every

        max_pending = max(workers * 2, 1)
        pending = {}
        next_index_to_write = 0
        next_index_to_submit = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            for chunk in chunked_iterable(input_file, args.chunk_size):
                future = submit_chunk(executor, chunk)
                pending[next_index_to_submit] = future
                next_index_to_submit += 1

                while len(pending) >= max_pending:
                    future = pending.pop(next_index_to_write)
                    drain_result(future.result())
                    next_index_to_write += 1

            while next_index_to_write < next_index_to_submit:
                future = pending.pop(next_index_to_write)
                drain_result(future.result())
                next_index_to_write += 1

    print(
        f"Finished. Processed {total_processed:,} lines, kept {total_kept:,}."
        f" Output written to {args.output_file}."
    )


if __name__ == "__main__":
    main()


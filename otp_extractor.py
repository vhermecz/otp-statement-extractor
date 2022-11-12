#!/usr/bin/env python3
import argparse
import csv
import collections
import glob
import os
import re
import sys

from PyPDF2 import PdfWriter, PdfReader
from PyPDF2.generic import ContentStream, NameObject
from PyPDF2.constants import PageAttributes as PG


def operation_iterator(reader):
    for page in list(reader.pages):
        content = page.get_contents()
        stream = ContentStream(content, page.pdf)
        for operation in stream.operations:
            yield operation


def extract_text_seqs(reader):
    in_text = False
    seq = None
    for op in operation_iterator(reader):
        if not in_text:
            if op == ([], b'BT'):
                in_text = True
                seq = []
        else:
            if op == ([], b'ET'):
                yield seq
                seq = None
                in_text = False
            elif op[1] == b'Tj':
                seq.append(op[0][0])


def is_otp_account_number(text):
    return isinstance(text, str) and bool(re.match("^1177\d\d\d\d-\d\d\d\d\d\d\d\d$", text))

def is_currency(text):
    return isinstance(text, str) and bool(re.match("^[A-Z]{3}$", text))    

def is_tx_date(text):
    return isinstance(text, str) and bool(re.match("^\d\d\.\d\d\.\d\d$", text))

def is_tx_date_range(text):
    return isinstance(text, str) and bool(re.match("^\d\d\.\d\d\.\d\d-\d\d\.\d\d\.\d\d$", text))

def number_from_huntext(text):
    """
    Numbers are formatted according to hungarian grammar:
    - Uses comma as the decimal 'point'
    - Uses dot as thousands separator
    """
    return text.replace(".", "").replace(",", ".")

AccInfo = collections.namedtuple('AccInfo', ['account_number', 'currency'])
def extract_account_number_info(seq):
    candidates = list(filter(is_otp_account_number, seq))
    if not candidates or len(candidates) > 1:
        return None
    currency = seq[-1].strip()
    if not is_currency(currency):
        currency = None
    return AccInfo(candidates[0], currency)

def extract_seq_records(seq):
    starts = [
        idx
        for idx in range(0, len(seq)-2)
        if is_tx_date(seq[idx]) and is_tx_date(seq[idx+2])
    ]
    terminator = [
        idx
        for idx in range(0, len(seq))
        if is_tx_date_range(seq[idx])
    ] + [len(seq)+2]
    if starts:
        starts.append(terminator[0]-1)  # Stop at end of seq or 'IDÕSZAK:€'
        for ss, se in zip(starts, starts[1:]):
            result = seq[ss:se]
            result[3] = number_from_huntext(result[3])
            result[1:2] = []  # always empty
            yield result

def extract_records(reader):
    acc_no = None
    currencies = {}
    for seq in extract_text_seqs(reader):
        acc_info = extract_account_number_info(seq)
        if acc_info:
            acc_no = acc_info.account_number
            if acc_info.currency:
                currencies[acc_no] = acc_info.currency
        else:
            prefix = [acc_no, currencies.get(acc_no, "NA")]
            for record in extract_seq_records(seq):
                yield prefix + record

Meta = collections.namedtuple('Meta', ['term'])
def extract_meta(reader):
    term = None
    # TODO owner
    for op in operation_iterator(reader):
        if op[1] == b'Tj' and len(op[0]) == 1:
            text = op[0][0]
            if is_tx_date_range(text):
                term = text
    return Meta(term)

Content = collections.namedtuple('Content', ['meta', 'records'])
def extract(fname):
    reader = PdfReader(fname)
    meta = extract_meta(reader)
    records = list(extract_records(reader))
    if not records:
        return None
    return Content(meta, records)

def main():
    parser = argparse.ArgumentParser(
        prog = 'otp_extractor',
        description = 'Extract records from otp statements',
    )
    parser.add_argument('source')
    parser.add_argument('-o', '--out')
    args = parser.parse_args()
    fp = sys.stdout
    if args.out:
        fp = open(args.out, "w")
    source = args.source
    if os.path.isdir(source):
        source = os.path.join(source, "**", "*.pdf")
    cout = csv.writer(fp)
    for fname in glob.glob(source, recursive=True):
        res = extract(fname)
        if res:
            for record in res.records:
                cout.writerow([res.meta.term] + record)
    fp.flush()
    if args.out:
        fp.close()

if __name__ == "__main__":
    main()

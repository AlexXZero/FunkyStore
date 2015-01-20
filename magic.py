# -*- coding: utf-8 -*-

import money
from datetime import datetime

"""

Funky Code Standard (MagicFSC1, MagicFSC2 implementation)
These codes is used to share money accounts, money/permission vouchers, server commands, etc.

MagicFSC1 code format:
xx-111[111]-*
x – head – code type definition. Consists of letters (case ignored) nor digits.
1 – ident – 3 or 6 digits, first three (usually) defines type of request, entrie block may be used
  to identify the origin of code.
* – data – usually 10-digit uniquie key. Depending on head/ident, data may contain any sentence
  of readable digits nor letters. Max length: 32 symbols.
Examples: z0-100000-9900000001, 00-100500-imacode111

MagicFSC2 code format (extends MagicFSC1):
xxx-222-111111-*[-*]...
2 – origin – digits, used to determine the oirgin of code.
* – data – max length extended to 64 symbols. There may be up to 8 data blocks.
Example: z0f-100000-899999-1234567890-1234567890

"""

COLLECTION_NAME = 'codes'
BANK_ACCOUNT = '__RESERVE'

# Iterate and compare using 'starts with'

H_NOTHING = ['00']
H_DUMMY = ['y', 'z']
H_SERVER_ACTION = ['1','2', '3', '4']
H_VOUCHER = ['s']
H_VOUCHER_REUSABLE = ['m']
H_ACCOUNT = ['7', 'a']
H_GIFT = ['8']

# Idents

I_MONEY = ['101']
I_TICKET_TP = ['450', '475']
I_TICKET_TP_KERNEL = ['499']

# Status codes

SCKV = {
	'SC_NOT_YET_IMPLEMENTED': -2,
	'SC_WTF': -1,
	'SC_OK': 0,
	'SC_GENERIC_FAULT': 100,
	'SC_GENERIC_PARSE_ERROR': 1000,
	'SC_ILLEGAL_CHARACTERS': 1001,
	'SC_BAD_FORMAT': 1002,
	'SC_NOT_ENOUGH_BLOCKS': 1003,
	'SC_UNSUPPORTED_CODE': 1101,
	'SC_BAD_BLOCK': 1102,
	'SC_ILLEGAL_EXTRA_BLOCK': 1103,
	'SC_GENERIC_QUERY_ERROR': 2000,
	'SC_NO_SUCH_CODE': 2001,
	'SC_EXPIRED_CODE': 2002,
	'SC_REVOKED_CODE': 2003,
	'SC_GENERIC_EXECUTION_ERROR': 3000,
	'SC_UNSUPPORTED_REQUEST': 3001,
	'SC_DEFECTIVE_CODE': 3002,
	'SC_WRONG_USAGE': 3003,
	'SC_MONEY_TRANSFER_FAILED': 3101
}

def reverse_map(d):
	return {v: k for k, v in d.iteritems()}

SCVK = reverse_map(SCKV)

def parse_code(code):
	out = {'status': SCKV['SC_OK']}
	if not code or len(code) < 2:
		return {'status': SCKV['SC_GENERIC_PARSE_ERROR']}
	code_cooked = code.strip().lower()
	if code_cooked[0] == '~':
		code_cooked = code_cooked[1:]
		out['dry_run'] = True
	for c in code_cooked:
		if not c.isalpha() and not c.isdigit() and not c == '-':
			return {'status': SCKV['SC_ILLEGAL_CHARACTERS']}
	blocks = code_cooked.split('-')
	if len(blocks) < 2:
		return {'status': SCKV['SC_NOT_ENOUGH_BLOCKS']}
	for b in blocks:
		if not len(b) or len(b) > 32:
			return {'status': SCKV['SC_BAD_FORMAT']}
	out['head'] = blocks[0]
	if len(blocks[0]) == 2: # MagicFSC1 format
		
		if len(blocks) < 3:
			return {'status': SCKV['SC_NOT_ENOUGH_BLOCKS']}
		if len(blocks) > 3:
			return {'status': SCKV['SC_ILLEGAL_EXTRA_BLOCK']}
		out['version'] = 1
		if not len(blocks[1]) == 3 and not len (blocks[1]) == 6:
			return {'status': SCKV['SC_BAD_BLOCK']}
		for c in blocks[1]:
			if not c.isdigit():
				return {'status': SCKV['SC_BAD_BLOCK']}
		out['ident'] = int(blocks[1])
		origin = 0
		if len(blocks[1]) == 6:
			out['origin'] = track_origin(int(blocks[1][3:6]))
		if len(blocks) == 3:
			out['data'] = blocks[2]

	elif len(blocks[0]) == 3: # MagicFSC2 format
		return {'status': SCKV['SC_NOT_YET_IMPLEMENTED']}
	else:
		return {'status': SCKV['SC_UNSUPPORTED_CODE']}

	return out

def process(code, db, login):
	def _proc(code, db, login):
		out = parse_code(code)
		if out['status']:
			return out

		dry_run = False
		if 'dry_run' in out:
			dry_run = out['dry_run']
		else:
			out['dry_run'] = dry_run
		if out['head'][1] == '0':
			dry_run = True
		query_keys = ['head', 'ident', 'data']
		entry = db[COLLECTION_NAME].find_one({i: out[i] for i in query_keys})
		if not entry:
			out['status'] = SCKV['SC_NO_SUCH_CODE']
			return out

		if not entry['left']:
			out['status'] = SCKV['SC_EXPIRED_CODE']
			return out
		if 'expiraion' in entry:
			out['expiraion'] = entry['expiraion']
			if datetime.now() >= out['expiraion']:
				out['status'] = SCKV['SC_EXPIRED_CODE']
				return out
		if 'revoked' in entry and entry['revoked']:
			out['revoked'] = True
			out['status'] = SCKV['SC_REVOKED_CODE']
			return out
		out['left'] = entry['left']
		if 'produced' in entry: out['produced'] = entry['produced']
		if 'comment' in entry: out['comment'] = entry['comment']
		if 'value' in entry: out['value'] = entry['value']

		def code_type(head, tags):
			for t in tags:
				if head.startswith(t): return True
			return False

		if code_type(out['head'], H_VOUCHER + H_VOUCHER_REUSABLE):
			out['description'] = 'Voucher'
			ident = str(out['ident'])[0:3]
			if ident in I_MONEY:
				out['description'] += ' (Money)'
				if not 'value' in out or not isinstance(out['value'], float):
					out['status'] = SCKV['SC_DEFECTIVE_CODE']
					return out
				if not dry_run:
					ok, msg = money.transfer(db, BANK_ACCOUNT, login, out['value'])
					if not ok:
						out['status'] = SCKV['SC_MONEY_TRANSFER_FAILED']
						out['message'] = msg
						return out

			else:
				out['status'] = SCKV['SC_UNSUPPORTED_REQUEST']
				return out

			if not dry_run:
				decrement_left_value(db, out)

		else:
			out['status'] = SCKV['SC_UNSUPPORTED_REQUEST']
			return out

		return out

	out = _proc(code, db, login)
	kill_list = ['head', 'ident', 'data']
	if out['status']:
		kill_list += ['origin']
	for k in kill_list:
		if k in out: del(out[k])
	out['status'] = str(out['status']) + ' (' + SCVK[out['status']] + ')'
	if 'left' in out and out['left'] < 0:
		out['left'] = 'Infinity'
	return out

def decrement_left_value(db, info):
	if info['dry_run'] or info['left'] < 1: return
	db[COLLECTION_NAME].update({i: info[i] for i in ['head', 'ident', 'data']},
		{'$set': {'left': info['left'] - 1}})
	info['left'] -= 1

def track_origin(n):
	# Code origin tracking
		if n == 0:
			return 'Undefined'
		elif n in [111, 222, 333, 444]:
			return 'Hand-crafted'
		elif n in [500, 555]:
			return 'Vanilla'
		elif n in range(1, 9):
			return 'Administrator single issue'
		elif n == 9:
			return 'Administrator issue'
		elif n in range(10, 75):
			return 'Single order'
		elif n in range(75, 99):
			return 'Multiple order'
		elif n == 99:
			return 'Mass production order'
		elif n in range(300, 330):
			return 'Promotional'
		elif n in range(400, 420):
			return 'Freeware'
		elif n in range(420, 425):
			return 'Beerware'
		elif n in range(425, 430):
			return 'Gifted'
		elif n in range(430, 440):
			return 'Found'
		elif n in range(440, 449):
			return 'Prize'
		elif n == 499:
			return 'Mined'
		elif n in [777, 768]:
			return 'From another universe'
		elif n in range(890, 990):
			return 'Unknown'
		elif n in range(990, 1000):
			return 'Unusual'
		else:
			return 'Serial issue #' + str(n)

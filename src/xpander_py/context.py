import sys
from datetime import datetime, timedelta
from subprocess import run as spawn, PIPE
from shlex import split as shlexSplit
from random import choice as randomChoice
from string import ascii_lowercase
from klembord import Selection


PHRASES = {}
Clipboard = Selection()
if sys.platform.startswith('linux'):
	Primary = Selection('PRIMARY')


_year = 'YEAR'
_month = 'MONTH'
_day = timedelta(days=1)
_week = timedelta(days=7)
_hour = timedelta(hours=1)
_minute = timedelta(minutes=1)
_second = timedelta(seconds=1)
CONTEXT = {
	'year': _year,
	'month': _month,
	'week': _week,
	'day': _day,
	'hour': _hour,
	'minute': _minute,
	'second': _second,
}


def genId(length=7):
	return ''.join(randomChoice(ascii_lowercase) for _ in range(length))


def timeFunc(period=0, unit=None, format='%Y-%m-%d'):
	now = datetime.now()
	if unit is None:
		return now.strftime(format)
	elif unit is _year:
		return now.replace(year=now.year + period).strftime(format)
	elif unit is _month:
		years = period // 12
		months = period % 12
		return now.replace(year=now.year + years, month=now.month + months) \
			.strftime(format)
	else:
		return (now + (period * unit)).strftime(format)


def run(command, dir=None, shell=False, stderr=False):
	proc = spawn(
		shlexSplit(command),
		cwd=dir,
		shell=shell,
		timeout=1,
		text=True,
		stdout=PIPE,
		stderr=PIPE,
	)
	if stderr:
		return proc.stderr.strip()
	else:
		return proc.stdout.strip()


def fillentry(name='', default='', width=15):
	htmlId = genId()
	template = """
<div class="xpander-fillin input-field inline">
	<input id="{id}" name="{name}" type="text" value="{value}" size="{width}">
	<label for="{id}">{name}</label>
</div>
"""
	return template.format(id=htmlId, name=name, value=default, width=width)


def fillmulti(name='', default='', width=20, height=5):
	htmlId = genId()
	template = """
<div class="xpander-fillin input-field inline">
	<textarea id="{id}" class="materialize-textarea" name="{name}" col="{width}" row="{height}">{default}</textarea>
	<label for="{id}">{name}</label>
</div>
"""
	return template.format(id=htmlId, name=name, width=width, height=height, default=default)


def fillchoice(*choices, name='', default=None):
	htmlId = genId()
	selectTemplate = """
<div class="xpander-fillin input-field inline">
	<select id="{id}" name="{name}">{options}</select>
	<label for="{id}">{name}</label>
</div>
"""
	optionTemplate = '<option value="{value}">{value}</option>'
	options = []
	if default:
		options.append(
			'<option selected value="{value}">{value}</option>'.format(value=default)
		)
	for choice in choices:
		options.append(optionTemplate.format(value=choice))
	return selectTemplate.format(id=htmlId, name=name, options='\n'.join(options))


def filloptional(text, name=''):
	htmlId = genId()
	template = """
<div class="xpander-fillin">
	<label>
		<input id="{id}" type="checkbox" name="{name}" value="{value}" />
		<span>{value}</span>
	</label>
</div>
"""
	return template.format(name=name, value=text, id=htmlId)


def key(key, state=None):
	template = "${{{{{key}{state}}}}}$"
	return template.format(key=key.upper(), state=':{state}'.format(state=state.upper()) if state else '')  # noqa


def clipboard():
	return Clipboard.get_text() or ''


def primary():
	return Primary.get_text() or ''


def phrase(name):
	if name in PHRASES:
		return PHRASES[name].render(CONTEXT)
	return ''


CONTEXT['time'] = timeFunc
CONTEXT['run'] = run
CONTEXT['fillentry'] = fillentry
CONTEXT['fillmulti'] = fillmulti
CONTEXT['fillchoice'] = fillchoice
CONTEXT['filloptional'] = filloptional
CONTEXT['key'] = key
CONTEXT['clipboard'] = clipboard
if sys.platform.startswith('linux'):
	CONTEXT['primary'] = primary
CONTEXT['phrase'] = phrase

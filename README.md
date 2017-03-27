# xpander

## About

Xpander is a text expander for Linux written in python.

You type an abbreviation and it's automatically expanded to a predefined block
of text called a phrase. This is useful when filling out forms, coding
and whenever else you need to write the same block of text over and over.
Each phrase is stored as JSON file in a user configurable directory, default
is ~/.phrases.

Xpander features full support for multiple keyboard layouts (up to 4),
filtering by window and token expansion:

* $| marks where cursor will be placed after expansion;
* $C is replaced by clipboard contents;

You can also mark a phrase as a command. In this case phrase contents are
interpreted as command line and it's output pasted instead.

When putting tabs in phrase body and setting sending method as keyboard
actual Tab keypresses are sent. This means you can fill several form fields in
one go, simply by separating with tabs.

## Background

I've been using AutoHotkey's hotstrings quite a bit on Windows and been looking
for something similar on Linux.

All I found was Autokey which doesn't appear to be maintened anymore and does
not play nice with multiple keyboard layouts, so I set out to write my own text
expander.

## Installation and Dependencies

For multiple keyboard layout support Xpander relies on
[xkb-switch](https://github.com/ierton/xkb-switch), I compiled it and packaged
for debian, you can find it
[here](https://github.com/OzymandiasTheGreat/xkb-switch/releases).

Other dependencies should be in the repositories for your distro:

`sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-glib-2.0 python3-xlib`

(You probably have most of these installed already if you're on a gnome based
distro.)

Recommended way to install is to skip installation and run from source. (I suck
at packaging.)

If you must install there's a deb in the releases.

You can also run
`sudo pip3 install https://github.com/OzymandiasTheGreat/xpander/archive/master.zip`

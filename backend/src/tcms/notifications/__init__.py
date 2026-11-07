"""Notification rendering, the bell's read model and email delivery (docs/02 §2.7; M7 D11–D13).

Sits beside `reporting` (above the domain modules): it renders rows written by any module into a title
and a link, reading keys through SQL like reporting does (docs/03 §5), and sends the mention emails and
the daily assignment digest.
"""

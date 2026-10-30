"""List auto-paged EEX segments (dialogue 3 lines, narration 4 lines per box page) whose
wrapped English leaves a single line alone on a page after a full one (a "widow" page).

  widows.py            -> report: file key kind lines, then the English
  widows.py --jp       -> also the Japanese (worker lists; notes/ only)
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import text, tl


def widows():
    tls = tl.load_tls()
    for n in tl.names():
        sc = tl.load(n)
        for k, e in sorted(tls.get(n, {}).items()):
            op = sc.kind.get(k)
            pg = text.PAGE.get(op)
            if not pg:
                continue
            ls = text.wrap(e, text.WIDTH[op], pg, op in text.SENT_PAGE).split('\n')
            pages = [ls[i:i + pg] for i in range(0, len(ls), pg)]
            for i in range(1, len(pages)):
                body = [x for x in pages[i] if x]
                if len(body) == 1 and pages[i][0] and len([x for x in pages[i - 1] if x]) == pg:
                    yield n, k, op, sc, e, len(ls)
                    break


def main():
    jp = '--jp' in sys.argv
    count = 0
    for n, k, op, sc, e, nl in widows():
        count += 1
        print('%s %s %s (%d lines, %d per page)' % (n, tl.key_str(k), text.KIND[op], nl, text.PAGE[op]))
        if jp:
            print('JP: ' + sc.segs[k].replace('\n', ' '))
        print('EN: ' + e)
        print()
    print('%d widow segments' % count)


if __name__ == '__main__':
    main()

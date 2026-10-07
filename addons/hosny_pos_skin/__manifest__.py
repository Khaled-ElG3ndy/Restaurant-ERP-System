{
    'name': 'Hosny POS Skin',
    'version': '19.0.46.0.0',
    'category': 'Point of Sale',
    'summary': 'One coherent look for the POS — the branches\' own navy/blue/green, rebuilt',
    'description': """
Hosny POS Skin
==============

A single authoritative skin for the Point of Sale, matching the till the
branches already use: navy command bar, periwinkle category band, green
price badge on every product, blue-grey ground.

It is deliberately the LAST stylesheet in ``point_of_sale._assets_pos``.
``pos_modern_ui``, ``hosny_pos_theme`` and ``hosny_pos_controls`` each style
the same screens with ``!important``; rather than unpick three years of
overrides, this module is loaded after all of them and settles the result in
one place. Depending on all three is what pins that order.

It also ships the webfonts. Every existing stylesheet asks for ``Cairo`` but
none of them ever loaded it, so the POS has been falling back to the system
sans this whole time. Cairo (text) and IBM Plex Sans Arabic (figures) are
bundled as woff2 — not fetched from Google — because the POS has to keep
working when the branch loses its line.

Version 19.0.4.0.0 redraws the product screen to the till sheet the
branches signed off (section 15 of ``skin.css``): a light sky command bar
with a blue workplace pill and a round cashier portrait, one white filter
row carrying the categories and the product search on a single line, a
deep navy catalogue ground, slate product tiles with the green price pill
centred on the top edge, and an order line that reads delete, quantity,
name, price. Button LABELS are untouched — the sheet mis-spells several of
them and the strings in ``hosny_pos_controls`` are the correct ones.

The same pass fixes a layout fault that predates it: with the numpad open,
``.pads`` would not shrink and the pad's own rows claimed 470px of a 700px
column, collapsing the order list to a 26px sliver.

Version 19.0.4.1.0 fixes the POS boot loader. The reduced-motion block
only capped animation *duration*, which does not stop an ``infinite``
animation — it runs a full cycle every 0.01ms, so core's four loader dots
strobed instead of resting, and any cashier with "reduce motion" on saw
that on every boot. The iteration count is now capped too, the preference
is restated last so nothing more specific outranks it, and the loader
takes the catalogue's navy instead of core's flat ``#222``.

Version 19.0.4.2.0 keeps the loader loading. 19.0.4.1.0 stilled the dots
outright under reduced motion, and a frozen spinner reads as "hung", not
as "calm" — the cashier cannot tell a slow branch line from a dead till.
The dots now pulse through opacity instead: nothing travels and nothing
scales, so the preference is honoured in substance, while the screen still
says it is working.

Version 19.0.5.0.0 redraws the command bar to the second reference sheet
(section 15.12) and drops it from 80px to 62px: deep navy behind the crest
and the restaurant name, breaking through angular blue-grey facets into
flat white under the controls. `.pos-topheader` computes `direction: ltr`
inside an otherwise `rtl` POS, so its angled backgrounds are pinned
against the RTL rewrite — left unpinned they mirror while the content
stays put, which lands the navy behind the controls and paints the brand
white-on-white for Arabic cashiers only.

Version 19.0.5.2.0 settles the order panel's control tiles (section
15.15). ``hosny_pos_controls`` hides the six tiles that are not on its
keep-list — core's customer, note, save and course buttons, the "more"
ellipsis, and ``pos_ui_clean``'s duplicate فاتورة جديدة — but section
15.14 set ``display: inline-flex`` on the same buttons under the
``:is(#hs,.pos)`` root, which carries id-level weight and outranked the
hide: all six came back and the panel read as four ragged rows of
fourteen instead of two even rows of eight. The hide is restated at the
skin's own weight. The same pass sizes every icon box wider than the
1.28em FontAwesome glyph it holds, so the declared gap to the label is
the gap that shows, unsquashes the hospitality tray (hospitality.css
pins ``flex: 0 0 27px``, and on a flex row the basis beats ``width``),
and stops the open numpad overflowing the panel — its two columns each
asked for a 250px minimum inside 424px, and in the RTL bundle the
overflow fell off the left edge.

Version 19.0.5.3.0 gives the order list the room back. The control
tiles, the numpad toggle and the footer buttons each lost a few pixels of
height and padding, which takes the block below the list from 299px to
248px on a 900px panel — all 51px of it to the lines the cashier is
keying against, one more visible orderline. A tile is 52px and a footer
button 48px, both still clear of the 44px touch target; on panels under
820px tall they are 46px and 44px.

Version 19.0.6.0.0 settles the filter row's product search (section 16).
It was a flex item sitting immediately after the last category pill with
the same 10px gap, so it read as one more pill; below 1400px it wrapped,
and on a 1024px till it came to rest ON TOP of الأسماك with half the
label showing through. It is now pinned out of the flow to the right edge
of the row at every width, with the pills wrapping in the space left.
`.category-list` computes `ltr` inside an otherwise `rtl` POS — eight
competing `direction` declarations in ``hosny_pos_controls``, the last of
which wins — so the offsets are pinned against the RTL rewrite the same
way the command bar's gradients are. The focus state loses the base
sheet's square `*:focus-visible` outline, which was drawn as a 2px
rectangle around the bare input inside a 999px pill; the pill itself
carries the state as a shadow, which follows the border radius.

Version 19.0.7.0.0 clears the command bar (section 17). 15.13 dressed it
in seven gradient layers — four angular facet bands on the bar and three
more on a `::before` haze — which put a row of diagonal stripes and a fog
directly behind the crest. All seven are replaced by a single sweep that
keeps the two-tone identity without a band or a veil in it: flat navy
under the brand, a soft fade, white under the controls. The stops are
absolute lengths capped by a percentage, because `.pos-leftheader` is a
fixed 390px block and pure percentages left the workplace pill sitting on
mid-blue on a 1024px till. The angle is pinned against the RTL rewrite
for the reason 15.12 documents. 17.1 then asserts that the brand block
itself paints nothing — `.pos-leftheader`, `.hs-brand`, the crest and
their pseudo-elements — so whichever of the five modules styling this
header was putting a light block behind the logo, the bar's own gradient
is now the only thing behind it.

Version 19.0.8.0.0 settles the command bar on one colour (section 18).
Three passes had split it into a dark half and a light half — a light
sky band, a faceted navy wash breaking into white, then a single
navy-to-white sweep — so the crest, the brand line and the workplace
pill each sat on a different ground, and where the ramp fell depended on
the till's width. The bar is now flat ``--hs-grid``: the same navy the
catalogue ground is mixed from, so the bar and the product field read as
one surface under the white filter row and the white order panel.

That also settles the logo. What production was actually serving is
15.13, whose ``::before`` haze includes a hard-edged wedge across the
top-left corner — a pale diagonal patch sitting directly behind the
crest, which is the "fog" the branches saw. Both painted layers stay
retired and the brand block is asserted to paint nothing, so the only
thing behind the logo is the bar's own colour.

The controls are re-set for a dark ground, since 15.1 drew them for a
light one: white lettering throughout, translucent icon tiles with a
hairline in place of pale-blue blocks, a slightly brighter workplace
pill, a white-ringed cashier portrait, and status colours lifted to
read on navy — a ``text-danger`` of #C6342D is how a cashier learns the
till has lost the branch line, and on navy it was barely a change at
all. A flat colour has no angle for rtlcss to mirror, so the bar also
leaves behind the whole class of RTL bug that 15.12 documents.

Version 19.0.9.0.0 puts a grade back on the command bar (section 19),
without putting the noise back. The second reference sheet crosses from
navy to near-white through four hard facet bands; the bands are the
noisy part, not the crossing. So the bar now carries one smooth ramp
held INSIDE the navy — deep behind the crest, lifting to a brighter
blue under the controls — which means nothing on it has to change
colour to stay legible: the white lettering, the translucent icon tiles
and the portrait ring from section 18 all read at both ends. The first
stop is held flat across the whole brand block, so the crest still sits
on one solid colour and 18's fix is not undone, and the angle is pinned
against the RTL rewrite for the reason 15.12 documents.

Version 19.0.10.0.0 turns the command bar over to the third reference
sheet (section 20): near-white under the crest, easing to a pale icy
blue under the controls with one wide soft sheen across it, the brand in
navy over a grey line, and the three controls drawn as solid blue — a
filled pill, the round portrait, a filled square tile. It is the reverse
of 18/19, so those sections' rules are restated rather than inherited;
the ones that would not have looked broken in review are the status
colours (18 lifted `text-danger` to #FF8F84 to survive navy, which is
invisible on white, and that indicator is how a cashier learns the till
is offline) and the split between the bar's lettering, now navy, and the
glyphs inside the filled controls, still white. What carries over is the
part that was never about colour: the brand block paints nothing and
both pseudo-element layers stay retired, and the base ramp holds flat
across the brand block, so whatever is behind the crest is one solid
surface with no patch on it.

Version 19.0.11.0.0 makes that ramp legible and drops the bar to 66px
(section 21). 20's sweep measured a ten-point drop spread over 1560px —
a gradient on paper, a flat white bar with a cool corner on the till; it
now goes deeper and ARRIVES at 86%, so the stretch under the controls is
a settled colour instead of one still travelling. The white plateau
under the crest is untouched. Everything in the bar is re-sized against
the new height in one place — crest, both type sizes, and all three
controls, which stop at the 44px touch target — because a shorter bar
still carrying a 50px crest reads as a crest crammed in rather than as a
shorter bar. 15.12's small-screen block is restated too: it still asked
for 64px, which would now be taller than the desktop bar.

Version 19.0.12.0.0 turns the card's price badge back round (section
22). It is built lead-then-value — "يبدأ من" first, the amount second —
with `dir="rtl"` stamped on it so the word sits at the right and the
price follows to its left. It was coming out reversed because
``hosny_pos_controls`` matches the badge from a long selector list that
declares `direction` three times, the last two `ltr`, and an author
declaration on the element beats the `[dir]` rule the browser applies.
Those are the broken-directive rules this project keeps hitting: the
ignore comment is written after the declaration, a position rtlcss does
not honour, so the Arabic bundle serves the opposite of the source.
Rather than unpick eight of them across two files, the direction is
asserted here with the directive in the position that works, pinned for
both bundles because the lead is Arabic whichever language the till runs
in; the inner value is pinned `ltr`, since a number followed by a
currency symbol is an LTR run in any language.

Version 19.0.13.0.0 rebuilds the workplace screen — the سفري / محلي
chooser a cashier meets first — to the reference sheet (section 23): a
white-to-periwinkle room with a cutlery roundel watermarked off the
leading edge and two leaf sprigs, a green eyebrow pill, a large navy
heading over a grey sub-line and a short green rule, then two wide white
cards with their copy on the inline-start side and an illustration
filling the rest. ``pos_entry_selector`` grows the parts that were not in
its markup at all — the sub-line, the rule, the watermark layer and the
two illustrations, all inline SVG — while its first-version orbs, grid
and gold arcs are hidden rather than deleted, so the screen still stands
up if this skin is uninstalled. The card grid's direction is pinned
instead of inherited: the module writes a bare `direction: rtl` that
rtlcss flips, so سفري sitting on the left — which is what the reference
shows — was an accident of the rewrite rather than a decision.

Version 19.0.14.0.0 brings the table map into the same room (section
24): the chooser's wash behind it, a white row of floor pills in place
of the navy band, and white table cards with a hairline and a soft drop.
The change that is a decision rather than a colour is the four per-floor
tints — sage for أرضي and one each for علوي، سفري، VIP — flattened to a
single white card. Which floor you are on is already answered by the lit
pill above; what a cashier reads this grid for is which tables are free,
and with the floor carrying a tint the state had nothing left to say
with. The card is now white and the STATE carries the colour: a green
dot and a green متاحة pill when free, amber and مشغولة with the amount
beside it when not. The order counter keeps its red — it is a count, and
the one thing on this screen that should interrupt.

Version 19.0.15.0.0 gives every floor its own colour and lays the
tables out as a grid (section 25), from three photographs of another
till: violet, blue, magenta and cyan cards, all one size in even rows,
with occupied tables in a deep red carrying the amount. It reverses
section 24's flattening with a better answer than either had alone —
the FLOOR owns the card colour and OCCUPIED overrides it with one red
everywhere, so a cashier reads the room by hue and the busy tables by
the one colour that is not a hue, the same on every floor. The tones
come from ``pos_entry_selector``'s ``getFloorTone()``, which matches the
floor's name; anything it does not recognise falls to a neutral slate.
The layout half returns each table to normal flow inside a grid, since
core positions them absolutely from the floor-plan editor's stored x/y
and pins their size inline — but only while the editor is CLOSED: inside
it those positions are the data being edited, and gridding them would
make the floor plan impossible to arrange.

Version 19.0.16.0.0 restates those four hues FLAT (section 26). 25 had
modernised them into short vertical ramps; the photographs show one
saturated fill per floor, so the ramps go and only the six tokens
change — the grid, the white numerals, the pills and the red override
all read the same tokens and are untouched. The values are read off
photographs of a screen rather than sampled, which the section says out
loud: a hex from the other system pins any of them exactly, in one line.

Version 19.0.25.0.0 takes the dotted grey off the printed bill (section
34). <body> carries ``.pos``, so ``pos_modern_ui``'s card rules for the
order panel — the cream container, the white line cards, the beige price
pill — matched the receipt as well, and the one-bit printer dithered each
pale fill into dots. Inside ``.pos-receipt`` only their paint is removed;
the layout is untouched. The same section colours the tick on the new
«تم الإرسال» state of the send button and styles its count pill.

Version 19.0.26.0.0 stops long bills printing cut off (section 34.1). The
same panel rules made the receipt's order box a shrinkable flex child inside
an ``overflow-hidden`` wrapper, so from about six lines it came out a few
pixels short and printed with scrollbars and a sliced last line; they also
trimmed the foot of every product name. On the bill the box now takes its
content's height and nothing clips — type and spacing are unchanged.

Version 19.0.27.0.0 makes an order line's quantity read as one number
(section 35). Fish is keyed in grams, and the fixed 40px chip broke 1750
into «17» over «50»; the chip now grows with the number on one line, a size
up, with the decimal part at full size. The counter on the product tile is
hidden, because it covered the price.

Version 19.0.28.0.0 gives every order line visible edges (section 36): the
list takes a pale grey-blue ground and each line is a white card with a full
border, where before a white line sat on a white list with at most a faint
hairline under it. The selected line keeps its mint fill in a mint frame,
and the delete button no longer loses 2px off its left edge.

Version 19.0.29.0.0 renames the bill button «فاتورة» to «طباعة» and removes
the «لوحة الأرقام» toggle from the order panel (``skin.xml``). The toggle was
the only way that numpad opened, so the numpad goes with it.

Version 19.0.30.0.0 pads the totals block (section 37): 16px inside a full
rounded border instead of 2px, the list's 14px side margins and 16px radius,
and room before the hairline under it, which loses its old gold tint.

Version 19.0.31.0.0 styles «عرض الطلب كاملاً» (section 38), whose
behaviour is in ``hosny_pos_controls``: the expand button held in the
bottom-left corner of the order list, a line's kitchen notes as amber
chips under its name (a line with notes lets go of the fixed 74px row
height), the order's own note as a labelled strip after the last line,
and the dialog itself — navy header, the lines on the right, the order
note and the totals on the left, the send button in the footer.

Version 19.0.32.0.0 styles the popup-free quantity entry (section 39),
whose behaviour is in ``hosny_pos_controls``: a small number grid to the
left of the order lines (the list and the grid share one row, the totals
run under both), a header naming what the keys type into, amber when that
is the discount, and an outline on the quantity chip being typed into.

Version 19.0.33.0.0 makes that pad a popover (section 39): hidden until
«الكمية» (or «نسبة الخصم», or a line's quantity chip) shows it OVER the
catalogue beside the order panel, gone again on the same button or any tap
outside, with a short fade-and-slide. The panel widening, the smaller tile
minimum and the narrower 1024px search that 19.0.32.0.0 needed are removed.

Version 19.0.34.0.0 brings «تقسيم الفاتورة» and «تحويل جزئي بين
الطاولات» into the same look, read from the right (section 40): Arabic
labels and the table on the split screen, the order panel's own cards with
the picked «1 / 2» on each line, a summary card instead of a 10vw figure,
and the transfer dialog's title made white again (section 29 coloured it
dark through a wildcard), its cards, stepper, tables and footer restyled.

Version 19.0.35.0.0 does the same for «الضيافة» (section 41): white title,
white cards with a mint tick and a mint price, footer buttons from the
right on one line, and Arabic empty states.

Version 19.0.36.0.0 puts the dialog titles on the right: the transfer
header spread its pill and title (they were packed together on the left),
the hospitality header no longer runs row-reverse to flex-end, and the merge
dialog's title takes the right with its badge on the left.

Version 19.0.37.0.0 styles the till opening straight on the cashier
(section 42), whose behaviour is in ``pos_entry_selector`` 19.0.2.0.0: a
white bar under the catalogue with a سفري / محلي switch and the table slot,
the table picker dialog, and the navbar's «الكاشير» pill in mint.

``static/src/xml/skin.xml`` adds presentation-only markup: section headings
over the catalogue and the order panel, the branch name in the command bar,
the «طباعة» label on the bill button, and correct Arabic plurals on the line
counter. It also removes the order panel's numpad toggle; nothing else opens
that numpad, since الكمية and نسبة الخصم use popups. It adds no Python and
no handlers, and changes nothing in order, pricing, payment or kitchen flow.
Uninstalling restores the previous look exactly.
""",
    'author': 'Hosny',
    'depends': [
        'point_of_sale',
        # skin.xml restyles pos_restaurant's split-bill screen
        'pos_restaurant',
        # Load order is the whole point: each of these styles the product
        # screen with !important, so the skin has to come after all of them.
        'pos_modern_ui',
        'hosny_pos_theme',
        'hosny_pos_controls',
        'pos_ui_clean',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hosny_pos_skin/static/src/css/fonts.css',
            'hosny_pos_skin/static/src/js/product_pager.js',
            'hosny_pos_skin/static/src/css/skin.css',
            'hosny_pos_skin/static/src/xml/product_pager.xml',
            'hosny_pos_skin/static/src/xml/skin.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

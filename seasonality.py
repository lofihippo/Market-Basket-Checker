"""Cited seasonal context, kept separate from observed sale-price history."""
USDA = 'https://snaped.fns.usda.gov/seasonal-produce-guide'
MASS = 'https://www.mass.gov/guides/pick-your-own-farms'
AMS = 'https://mymarketnews.ams.usda.gov/viewReport/3324'

_SEASONS = {'spring': [3, 4, 5], 'summer': [6, 7, 8],
            'fall': [9, 10, 11], 'winter': [12, 1, 2]}
# USDA identifies seasons, not precise harvest months. The month mapping is
# an explicit presentation convention, not a finer-grained USDA prediction.
_ITEMS = [
    ('Apples', ['spring', 'summer', 'fall', 'winter'], [8, 9, 10, 11]),
    ('Asparagus', ['spring'], []),
    ('Strawberries', ['spring', 'summer'], [6, 7]),
    ('Blueberries', ['summer'], [7, 8]),
    ('Peaches', ['summer'], [7, 8, 9]),
    ('Corn', ['summer'], []),
    ('Tomatoes', ['summer'], []),
    ('Bell peppers', ['summer', 'fall'], []),
    ('Broccoli', ['spring', 'fall'], []),
    ('Grapes', ['summer', 'fall', 'winter'], []),
    ('Pears', ['summer', 'fall', 'winter'], []),
    ('Cranberries', ['fall'], []),
    ('Pumpkin', ['fall', 'winter'], [9, 10]),
    ('Winter squash', ['fall', 'winter'], []),
    ('Potatoes', ['fall', 'winter'], []),
    ('Sweet potatoes', ['fall', 'winter'], []),
    ('Oranges', ['winter'], []),
    ('Carrots', ['spring', 'summer', 'fall', 'winter'], []),
]


def seasonal_context():
    items = []
    for name, seasons, regional in _ITEMS:
        note = ('Massachusetts picking season is shown as a New England reference; '
                'timing varies by state, crop variety, and weather.' if regional else
                'No regional harvest window has been added for this item.')
        items.append({'name': name,
                      'months': sorted({m for season in seasons for m in _SEASONS[season]}),
                      'seasons': seasons, 'new_england_months': regional,
                      'source_url': USDA, 'regional_source_url': MASS if regional else None,
                      'note': note})
    return {
        'months': 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(),
        'items': items, 'reviewed_at': '2026-09-14',
        'note': ('USDA seasonal availability is context, not a prediction of discounts. '
                 'For display, spring means Mar–May, summer Jun–Aug, fall Sep–Nov, '
                 'and winter Dec–Feb. Actual availability varies by origin and weather. '
                 'Regional notes use Massachusetts picking windows as a New England example.'),
        'sources': [
            {'title': 'USDA SNAP-Ed Seasonal Produce Guide', 'url': USDA,
             'note': 'National seasonal produce guidance; does not prescribe sale dates or prices.'},
            {'title': 'Massachusetts Department of Agricultural Resources', 'url': MASS,
             'note': 'Local picking windows for apples, berries, peaches, and pumpkins. Months include partial-month windows.'},
            {'title': 'USDA AMS Weekly Grocery Store Specialty Crops Feature Activity', 'url': AMS,
             'note': 'National and regional advertised produce-price survey. Reference only: no national price data has been imported or compared here.'},
        ],
    }

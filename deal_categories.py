"""Attach transparent report categories without changing extracted offers."""
import copy
import html
import re
import unicodedata


def normalized_name(value):
    value = unicodedata.normalize('NFKC', html.unescape(value or '')).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', value))


_DEPARTMENTS = {
    'bakery': 'Bakery', 'beer-wine-and-spirits': 'Beer & Wine',
    'cheese-shoppe': 'Cheese Shoppe', 'dairy': 'Dairy & Frozen Foods',
    'deli': 'Delicatessen', 'grocery': 'Grocery', 'markets-cafe': 'Café',
    'markets-kitchen': 'Prepared Foods', 'meat': 'Meat', 'produce': 'Produce',
    'seafood': 'Seafood', 'sushi': 'Sushi',
}
# Estimates are deliberately labeled. They are not retailer inventory counts.
_RULES = [
    ('Household & Pet', r'\b(detergent|dish\s*(soap|liquid)|paper towels?|bath tissue|toilet|bleach|trash|garbage|cleaner|disinfect|dog food|cat food|cat litter|kibbles|purina|friskies|fancy feast|dixie|bounty|charmin|puffs tissues|reynolds|hefty|ziploc|glad bags|shampoo|toothpaste|deodorant|soap|vitamins?)\b'),
    ('Floral', r'\b(roses|bouquet|potted|mums|bromeliad|heather|sunflower bunch|orchid|chrysanthemum)\b'),
    ('Beer & Wine', r'\b(wines?|cabernet|chardonnay|merlot|pinot|sauvignon|beer|budweiser|bud light|coors|miller lite|michelob|cavit|coppola|wente|casillero|high noon|nutrl|sun cruiser|truly hard|samuel adams|heineken|corona extra)\b'),
    ('Sushi', r'\b(sushi|nigiri|tempura.*roll|teriyaki chicken roll|rainbow roll)\b'),
    ('Seafood', r'\b(shrimp|scallops?|haddock|cod fillets?|salmon|lobster|swordfish|tilapia|smelts?|quahogs?|herring|crab|clams?|fish|seafood|flounder|mussels?|tuna steaks?)\b'),
    ('Bakery', r'\b(bread|bagels?|muffins?|cakes?|cookies|croissants?|donuts?|doughnuts?|whoopie|brownies|bundt|fudge|pies?|dinner rolls?)\b'),
    ('Dairy & Frozen Foods', r'\b(yogurt|skyr|milk|eggs|cream cheese|sour cream|ice cream|frozen|creamer|butter|margarine|cottage cheese|whipped cream|shredded cheese|cheese slices|popsicles|frozen waffles)\b'),
    ('Meat', r'\b(beef|steaks?|roast|pork|ham|chicken|turkey|lamb|bacon|sausage|franks|kielbasa|ribs|burger|pepperoni|salami|lunchmakers|quail|tenderloin|drumsticks|thighs|poultry)\b'),
    ('Produce', r'\b(apples?|pears?|grapes|bananas?|berries|blackberries|blueberries|strawberries|raspberries|cranberries|potatoes|squash|pumpkins?|peas|lettuce|salad kits?|salads kits|chopped kit|spinach|broccoli|cauliflower|carrots|corn|peppers?|cucumbers?|tomatoes|kiwi|kiwifruit|avocados?|melons?|peaches|nectarines|plums|oranges|lemons|limes|mushrooms|onions|asparagus|cabbage|celery|green beans|vegetables|romaine|herbs|zucchini|eggplant|beets)\b'),
    ('Grocery', r'\b(pasta|sauce|soup|rice|beans|cereal|oats|oatmeal|coffee|tea|juice|soda|coke|pepsi|seltzer|water|chips|tostitos|crackers|snacks?|popcorn|nuts|peanut butter|jam|jelly|oil|vinegar|dressing|ketchup|mustard|mayonnaise|flour|sugar|candy|chocolate|granola|tortillas?|horseradish|baking)\b'),
]
_COMPILED = [(category, re.compile(pattern, re.I)) for category, pattern in _RULES]


def classify_offer(offer, catalog=()):
    name = normalized_name(offer.get('item'))
    # Separate non-food shopping categories even when the retailer files them
    # under its broader Produce or Grocery departments.
    for category, pattern in _COMPILED[:2]:
        if pattern.search(name):
            return category, 'Estimated from item words'
    tokens = set(name.split())
    exact, contained = set(), set()
    for product in catalog:
        product_name = normalized_name(product.get('name'))
        departments = {_DEPARTMENTS[d.get('slug')] for d in product.get('departments', [])
                       if d.get('slug') in _DEPARTMENTS}
        if product_name == name:
            exact.update(departments)
        elif len(tokens) >= 2 and tokens <= set(product_name.split()):
            contained.update(departments)
    if len(exact) == 1:
        return next(iter(exact)), 'Official department: exact name match'
    # A narrower printed title can be used for category only, not SKU identity.
    if not exact and len(contained) == 1:
        return next(iter(contained)), 'Official department: name-based category match'
    for category, pattern in _COMPILED:
        if pattern.search(name):
            return category, 'Estimated from item words'
    return 'Uncategorized', 'No reliable category match'


def categorize_payload(payload, catalog=()):
    result = copy.deepcopy(payload)
    for page in result['pages']:
        for deal in page['deals']:
            deal['category'], deal['category_source'] = classify_offer(deal, catalog)
    return result

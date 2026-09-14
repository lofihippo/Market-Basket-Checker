import unittest

from deal_categories import categorize_payload, classify_offer
from seasonality import seasonal_context


class ReportContextTests(unittest.TestCase):
    def test_department_matching_does_not_change_names_or_prices(self):
        original = {'pages': [{'page': 0, 'deals': [{'item': 'Example Soup', 'price': '2 for $5'}]}]}
        catalog = [{'name': 'Example Soup', 'departments': [{'slug': 'deli'}]}]
        result = categorize_payload(original, catalog)
        self.assertEqual(result['pages'][0]['deals'][0]['category'], 'Delicatessen')
        self.assertEqual(original['pages'][0]['deals'][0], {'item': 'Example Soup', 'price': '2 for $5'})

    def test_ambiguous_catalog_category_uses_labeled_estimate(self):
        catalog = [{'name': 'Fresh Chicken', 'departments': [{'slug': slug}]} for slug in ('meat', 'deli')]
        category, reason = classify_offer({'item': 'Fresh Chicken'}, catalog)
        self.assertEqual(category, 'Meat')
        self.assertIn('Estimated', reason)
        self.assertEqual(classify_offer({'item': 'Unidentified Special'})[0], 'Uncategorized')

    def test_floral_and_household_do_not_count_as_grocery_produce(self):
        self.assertEqual(classify_offer({'item': 'One Dozen Roses'})[0], 'Floral')
        self.assertEqual(classify_offer({'item': 'Dixie Plates'})[0], 'Household & Pet')
        self.assertEqual(classify_offer({'item': 'Polar Seltzer'})[0], 'Grocery')

    def test_seasonal_context_distinguishes_national_and_local_availability(self):
        result = seasonal_context()
        items = {i['name']: i for i in result['items']}
        self.assertEqual(items['Apples']['months'], list(range(1, 13)))
        self.assertEqual(items['Apples']['new_england_months'], [8, 9, 10, 11])
        self.assertEqual(items['Blueberries']['months'], [6, 7, 8])
        self.assertEqual(items['Blueberries']['new_england_months'], [7, 8])
        self.assertEqual(items['Asparagus']['new_england_months'], [])
        self.assertIn('not a prediction', result['note'])
        self.assertEqual(len(result['sources']), 3)


if __name__ == '__main__':
    unittest.main()

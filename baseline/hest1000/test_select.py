import unittest
from baseline.hest1000.select import select

class SelectionTests(unittest.TestCase):
    def test_input_order_does_not_change_selected_ids(self):
        rows=[dict(id=str(i), species='mouse', st_technology='ST', organ='brain') for i in range(10)]
        a,_,_=select(rows,6); b,_,_=select(list(reversed(rows)),6)
        self.assertEqual([r['id'] for r in a],[r['id'] for r in b])

    def test_rare_stratum_retained(self):
        rows=[dict(id=str(i), species='mouse', st_technology='ST', organ='brain') for i in range(10)]
        rows.append(dict(id='rare',species='human',st_technology='HD',organ='kidney'))
        chosen,_,quota=select(rows,6)
        self.assertIn('rare',[r['id'] for r in chosen]); self.assertEqual(sum(quota.values()),6)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError): select([{'id':'x'},{'id':'x'}],1)

    def test_too_many_strata_rejected(self):
        with self.assertRaises(ValueError): select([dict(id='x',organ='a'),dict(id='y',organ='b')],1)

if __name__=='__main__': unittest.main()

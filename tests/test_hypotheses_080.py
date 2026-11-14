import json,unittest
from pathlib import Path
from copy import deepcopy
from kardiaos.hypotheses import merge_hypotheses,visible_hypotheses,ALIASES
from kardiaos.review_window import template_supported,select_lead as select_signal_quality
from kardiaos.research import catalog
CAT=catalog()

def fixture(model,code,value,first=20):
    spec=CAT['models'][model];label=next(z for z in spec['labels'] if z['code']==code)
    return dict(model=model,mode='normal',first_sample=first,last_sample_exclusive=3020,
        checkpoint_sha256=spec['sha256'],scores=[dict(label,score=value)],preprocessing={'fixture':True},source_key='TEST-ONLY')

class Presentation(unittest.TestCase):
    def test_exact_semantic_max_and_all_sources(self):
        rows=[fixture('ecgfounder_1l','ECGF-005',.2),fixture('deeppsp_2l','164889003',.7),fixture('deeppsp_6l','164889003',.4)]
        original=deepcopy(rows);r=merge_hypotheses(rows,20,3020,CAT)
        self.assertEqual(len(r['rows']),1);v=r['rows'][0]
        self.assertEqual(v['score'],.7);self.assertEqual(v['winning_model'],'deeppsp_2l')
        self.assertEqual(len(v['sources']),3);self.assertFalse(v['calibrated_probability']);self.assertEqual(rows,original)
    def test_distinct_conditions_never_fuzzy_merged(self):
        rows=[fixture('ecgfounder_1l','ECGF-001',.4),fixture('ecgfounder_1l','ECGF-003',.5),fixture('deeppsp_2l','164889003',.7),fixture('deeppsp_2l','164890007',.6)]
        self.assertEqual(len(merge_hypotheses(rows,20,3020,CAT)['rows']),4)
    def test_scope_and_bad_scores(self):
        rows=[fixture('deeppsp_2l','164889003',.7,first=21),fixture('deeppsp_2l','164890007',float('nan'))]
        r=merge_hypotheses(rows,20,3020,CAT);self.assertEqual(r['rows'],[]);self.assertEqual(len(r['rejected']),2)
    def test_alias_catalog_contract(self):
        a={z['code']:z['name'].casefold() for z in CAT['models']['ecgfounder_1l']['labels']}
        b={z['code']:z['name'].casefold() for z in CAT['models']['deeppsp_2l']['labels']}
        for code,(canonical,name) in ALIASES.items():self.assertEqual(a[code],name);self.assertEqual(b[canonical],name)
    def test_no_empty_square(self):
        for q,gs in ((True,[]),(False,[dict(technical_eligible=True)]),(True,[dict(technical_eligible=False)])):
            self.assertFalse(template_supported(dict(quality={'eligible':q},template={'groups':gs})))
        self.assertTrue(template_supported(dict(quality={'eligible':True},template={'groups':[dict(technical_eligible=True)]})))
    def test_visible_max3_no_score_name_kept(self):
        merged=dict(rows=[dict(label=str(i),score=i/10,winning_model_name='Actual model') for i in range(7)])
        view=visible_hypotheses(merged);self.assertEqual(len(view),3)
        self.assertTrue(all(set(v)=={'label','model'} for v in view));self.assertEqual(visible_hypotheses({'rows':[]}),[])
        self.assertEqual(len(visible_hypotheses({'rows':merged['rows'][:1]})),1)
    def test_T_quality_selector_ignores_values_and_availability(self):
        def entry(q,flags):return dict(quality={'eligible':True,'score':q},template={'eligible_beats':7,'groups':[dict(n_beats=7,reasons=flags)]},result={'qtc_f':500})
        entries={'I':entry(.99,['possible_T_alternation']),'II':entry(.90,[])}
        self.assertEqual(select_signal_quality(entries)[0],'II')
        entries['I']['result']['qtc_f']=200;entries['II']['result']['qtc_f']=None
        entries['II']['template']['groups'][0]['reasons'].append('model_template_disagreement')
        self.assertEqual(select_signal_quality(entries)[0],'II')
        self.assertNotIn('result',select_signal_quality(entries)[1]['II'])

if __name__=='__main__':unittest.main(verbosity=2)

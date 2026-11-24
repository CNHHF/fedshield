import unittest
from backend.engine.rule_schema import compile_spec,validate_expression
from backend.compliance.rule_engine import evaluate
class TestAIRuleConfiguration(unittest.TestCase):
    def test_disconnected_action_and_independent_branches(self):
        r={'code':'GRAPH','enabled':True,'nodes':[{'id':'t','type':'trigger','config':{'event':'data.transfer'}},{'id':'a','type':'condition','name':'欧盟','config':{'field':'targetRegion','op':'eq','value':'EU'}},{'id':'b','type':'condition','name':'高金额','config':{'field':'amount','op':'gt','value':10000}},{'id':'stop','type':'action','config':{'action':'block'}},{'id':'audit','type':'action','config':{'action':'audit'}}],'edges':[{'source':'t','target':'a'},{'source':'t','target':'b'},{'source':'a','target':'stop'},{'source':'b','target':'audit'}]}
        ctx={'event':'data.transfer','targetRegion':'EU','amount':200}
        self.assertFalse(evaluate([r],ctx)['passed'])
        r['edges']=[e for e in r['edges'] if e['target']!='stop']
        self.assertTrue(evaluate([r],ctx)['passed'])
        self.assertFalse(any(a['action']=='block' for a in evaluate([r],ctx)['actions']))
    def test_and_or_amount_and_actions(self):
        expr={'all':[{'field':'targetRegion','op':'eq','value':'EU'},{'any':[{'all':[{'field':'amount','op':'gt','value':10000},{'field':'authorized','op':'eq','value':False}]},{'field':'hasDpia','op':'eq','value':False}]}]}
        rule=compile_spec({'name':'欧盟要件检查','condition':expr,'actions':[{'action':'block','message':'补齐要件'},{'action':'notify','message':'核查记录'}]})
        self.assertFalse(rule['enabled']);rule.update(code='TEST-AI',enabled=True)
        def result(**kwargs):return evaluate([rule],{'event':'data.transfer','targetRegion':'EU','amount':200,'authorized':True,'hasDpia':True,**kwargs})
        self.assertTrue(result()['passed'])
        self.assertFalse(result(amount=20000,authorized=False)['passed'])
        self.assertFalse(result(hasDpia=False)['passed'])
        self.assertTrue(result(targetRegion='US',hasDpia=False)['passed'])
        self.assertEqual(len(rule['edges']),3)
    def test_schema_rejects_unknowns_wrong_types_and_excessive_tree(self):
        for expr in [{'field':'password','op':'eq','value':'x'},{'field':'amount','op':'gt','value':True},{'field':'authorized','op':'eq','value':'false'},{'any':[]},{'field':'amount','op':'regex','value':'.*'}]:
            with self.assertRaises(ValueError):validate_expression(expr)
        with self.assertRaises(ValueError):validate_expression({'field':'amount','op':'gt','value':10**1000})
        expr={'field':'authorized','op':'eq','value':False}
        for _ in range(6):expr={'all':[expr]}
        with self.assertRaises(ValueError):validate_expression(expr)
    def test_no_arbitrary_actions_or_generated_code(self):
        with self.assertRaises(ValueError):compile_spec({'name':'x','condition':{'field':'authorized','op':'eq','value':False},'actions':[{'action':'shell','message':'x'}]})
        with self.assertRaises(ValueError):compile_spec({'needsClarification':'需补充币种'})

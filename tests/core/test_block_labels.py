import copy
import unittest
import block_labels
import default_melody
import emotion_input as ui
import story_engine as e


class BlockLabelsTests(unittest.TestCase):
    def plan(self):
        p=ui.default_story();p['sources']=[default_melody.source()]
        return e.plan(p)

    def test_source_position(self):
        q=self.plan();label=block_labels.labels(q,q['blocks'][0])
        self.assertIn('第1块',label['short']);self.assertIn('欢乐颂',label['full'])

    def test_kept_source_and_generated_bridge_distinct(self):
        q=self.plan();keep=next(b for b in q['blocks'] if b['kind']=='transition_keep')
        bridge=next(b for b in q['blocks'] if b['kind']=='bridge')
        self.assertIn('原旋律',block_labels.labels(q,keep)['short'])
        self.assertIn('新生成',block_labels.labels(q,bridge)['short'])
        self.assertNotIn('第3块',block_labels.labels(q,bridge)['short'])

    def test_variant_uses_source_position_not_output_order(self):
        p=ui.default_story();p['sources']=[default_melody.source()]
        # Test variant labels independently of the peak's original-melody restart.
        p['auto_peak_memory']=False
        q=e.plan(p);block=next(b for b in q['blocks'] if b['version']=='variant' and b['source_spans'])
        label=block_labels.labels(q,block)
        first=block['source_spans'][0]['start']//1920+1
        self.assertIn('变体',label['full']);self.assertIn(f'第{first}块',label['full'])

    def test_partial_span(self):
        q=self.plan();block=copy.deepcopy(q['blocks'][0]);block['source_spans'][0]['start']=240
        self.assertIn('部分',block_labels.labels(q,block)['full'])


if __name__=='__main__':unittest.main()

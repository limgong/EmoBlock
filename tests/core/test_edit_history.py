"""Undo/redo branch rules independent of Tk."""
import unittest
from edit_history import EditHistory


class EditHistoryTests(unittest.TestCase):
    def test_undo_and_redo_walk_three_edits_in_order(self):
        h=EditHistory();states=[dict(v=i) for i in range(4)]
        for i,label in enumerate(('A','B','C')):self.assertTrue(h.record(states[i],states[i+1],label))
        current=states[3]
        for expected,label in ((2,'C'),(1,'B'),(0,'A')):
            current,got=h.undo(current);self.assertEqual((current,got),(states[expected],label))
        self.assertFalse(h.can_undo);self.assertEqual(h.redo_label,'A')
        for expected,label in ((1,'A'),(2,'B'),(3,'C')):
            current,got=h.redo(current);self.assertEqual((current,got),(states[expected],label))
        self.assertFalse(h.can_redo);self.assertEqual(h.undo_label,'C')

    def test_new_edit_after_undo_discards_redo_branch(self):
        h=EditHistory();h.record({'v':0},{'v':1},'A');h.record({'v':1},{'v':2},'B')
        current,_=h.undo({'v':2});self.assertTrue(h.can_redo)
        h.record(current,{'v':9},'C')
        self.assertFalse(h.can_redo);self.assertEqual(h.undo_label,'C')
        with self.assertRaises(ValueError):h.redo({'v':9})

    def test_unchanged_edit_keeps_history_and_redo(self):
        h=EditHistory();h.record({'v':0},{'v':1},'A');current,_=h.undo({'v':1})
        self.assertFalse(h.record(current,dict(current),'noop'))
        self.assertEqual((len(h),h.redo_label),(0,'A'))

    def test_snapshots_are_isolated_from_later_mutation(self):
        h=EditHistory();before={'curve':[1]};h.record(before,{'curve':[2]},'A')
        before['curve'].append(99)
        restored,_=h.undo({'curve':[2]});self.assertEqual(restored,{'curve':[1]})
        restored['curve'].append(5);again,_=h.redo({'curve':[1]});h.undo(again)
        self.assertEqual(h.redo_stack[-1][1],{'curve':[2]})

    def test_limit_and_clear(self):
        h=EditHistory(limit=3)
        for i in range(5):h.record({'v':i},{'v':i+1},str(i))
        self.assertEqual([label for label,_ in h.undo_stack],['2','3','4'])
        h.undo({'v':5});h.clear();self.assertFalse(h.can_undo or h.can_redo)


if __name__=='__main__':unittest.main()

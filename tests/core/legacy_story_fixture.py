"""Explicit old-project fixture: new projects intentionally start with an empty strip."""
import emotion_input
import default_melody
import story_engine


def restore_legacy(app):
    project=emotion_input.default_story()
    project['sources']=[default_melody.source()]
    project['continuous_intensity']=True
    app.story_page.restore(story_engine.automatic_memory_project(emotion_input.normalize(project)))
    app.init_persistence()

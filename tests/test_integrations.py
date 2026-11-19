import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from integrations import analyze_item, provider_info, transcribe_item


class IntegrationsTest(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(provider_info()["available"])
            with self.assertRaises(ValueError): analyze_item({"body":"exemple"})

    def test_local_model_needs_no_key_and_only_sends_selected_text(self):
        sample = {"source":"Rendez-vous fictif","body":"Annotation personnelle","audio":"enregistrement privé"}
        with patch.dict(os.environ,{"CERVEAU_AI_MODEL":"qwen2.5:7b"},clear=True):
            info = provider_info()
            self.assertTrue(info["available"])
            self.assertTrue(info["local"])
            client = Mock()
            client.open.return_value = io.BytesIO(b'{"choices":[{"message":{"content":"Reponse locale"}}]}')
            with patch("integrations.build_opener",return_value=client):
                self.assertEqual(analyze_item(sample),"Reponse locale")
            req = client.open.call_args.args[0]
            self.assertEqual(req.full_url,"http://127.0.0.1:11434/v1/chat/completions")
            payload = json.loads(req.data)
            self.assertEqual(payload["messages"][-1],{"role":"user","content":sample["source"]})
            self.assertNotIn("Annotation",str(payload))
            self.assertNotIn("enregistrement",str(payload))

    def test_remote_requires_https_and_key_and_supports_anthropic(self):
        with patch.dict(os.environ,{"CERVEAU_AI_MODEL":"claude-sonnet","CERVEAU_AI_URL":"http://api.anthropic.com/v1/messages","CERVEAU_AI_API_KEY":"synthetic"},clear=True):
            self.assertFalse(provider_info()["available"])
        with patch.dict(os.environ,{"CERVEAU_AI_MODEL":"claude-sonnet","CERVEAU_AI_URL":"https://api.anthropic.com/v1/messages","CERVEAU_AI_PROVIDER":"Claude","CERVEAU_AI_API_KEY":"synthetic"},clear=True):
            info = provider_info()
            self.assertTrue(info["available"])
            self.assertFalse(info["local"])
            self.assertEqual(info["name"],"Claude · claude-sonnet")
            client = Mock()
            client.open.return_value = io.BytesIO(b'{"content":[{"type":"text","text":"Reponse externe"}]}')
            with patch("integrations.build_opener",return_value=client):
                self.assertEqual(analyze_item({"source":"RDV vendredi"}),"Reponse externe")
            req = client.open.call_args.args[0]
            self.assertEqual(req.get_header("X-api-key"),"synthetic")
            self.assertEqual(req.get_header("Anthropic-version"),"2023-06-01")

    def test_decoder_refuses_non_audio(self):
        with self.assertRaises(ValueError):
            transcribe_item({"audio":"data:audio/wav;base64,YWJj"})

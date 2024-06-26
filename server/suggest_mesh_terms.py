from tevatron.faiss_retriever.__main__ import pickle_load
from tevatron.faiss_retriever.retriever import BaseFaissIPRetriever
from transformers import AutoConfig, AutoTokenizer
from tevatron.modeling.dense import DenseModel
from suggest_engine import Suggestion
import os
from itertools import chain
import json
from gensim.models import KeyedVectors
from gensim.utils import tokenize
import numpy
import scipy


class Suggest_MeSH_Terms_With_BERT(Suggestion):
    def __init__(self, params):
        super().__init__(params)
        self.params = params
        self.input_dict = self.params['payload']
        self.model = self.params['model']
        self.tokenizer = self.params['tokenizer']
        self.retriever = self.params['retriever']
        self.look_up = self.params['look_up']
        self.mesh_dict = self.params['mesh_dict']
        self.model_w2v = self.params['model_w2v']

    def suggest(self):
        type = self.input_dict["Type"]
        keywords = self.input_dict["Keywords"]
        if len(keywords) > 0:
            return_list = []
            if len(keywords) == 1:
                type = "Atomic"
            if type == "Atomic":
                for keyword in keywords:
                    suggestion_uids = keyword_suggestion_method(keyword, self.model, self.tokenizer, self.retriever,
                                                                self.look_up)
                    mesh_terms = get_mesh_terms(suggestion_uids, self.mesh_dict)
                    new_dict = {
                        "Keywords": [keyword],
                        "type": type,
                        "MeSH_Terms": mesh_terms
                    }
                    return_list.append(new_dict)
                return return_list
            elif type == "Semantic":
                keyword_groups = seperate_keywords_group(keywords, self.model_w2v)
                for keywords in keyword_groups:
                    suggestion_uids = semantic_suggestion_method(keywords, self.model, self.tokenizer, self.retriever,
                                                                 self.look_up)
                    mesh_terms = get_mesh_terms(suggestion_uids, self.mesh_dict)
                    new_dict = {
                        "Keywords": keywords,
                        "type": type,
                        "MeSH_Terms": mesh_terms
                    }
                    return_list.append(new_dict)
                return return_list
            elif type == "Fragment":
                suggestion_uids = fragment_suggestion_method(keywords, self.model, self.tokenizer, self.retriever,
                                                             self.look_up)
                mesh_terms = get_mesh_terms(suggestion_uids, self.mesh_dict)
                new_dict = {
                    "Keywords": keywords,
                    "type": type,
                    "MeSH_Terms": mesh_terms
                }
                return_list.append(new_dict)
                return return_list

            else:
                raise Exception("Type not valid")
        else:
            raise Exception("Minimum one keyword to suggest")


def get_mesh_terms(uids, mesh_dict):
    mesh_terms = {index: mesh_dict[uid] for index, uid in enumerate(uids) if uid in mesh_dict}
    return mesh_terms


def load_mesh_dict(path):
    mesh_dict = {}
    with open(path, 'r') as f:
        full_list = json.load(f)
        for item in full_list:
            uid = item['uid']
            original_term = item['term']
            mesh_dict[uid] = original_term
    return mesh_dict


def prepare_model():
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
    cwd = os.getcwd() + '/'
    # load mesh_dict
    mesh_path = cwd + "data/mesh2.json"
    mesh_dict = load_mesh_dict(mesh_path)

    # load_model_for_query_encoding
    num_labels = 1
    config = AutoConfig.from_pretrained(
        cwd + "Model/checkpoint-80000/",
        num_labels=num_labels,
        cache_dir="cache/",
    )
    model = DenseModel.load(
        model_name_or_path=cwd + "Model/checkpoint-80000/",
        config=config,
    )
    tokenizer = AutoTokenizer.from_pretrained("dmis-lab/biobert-v1.1", cache_dir="cache/")

    # load_mesh_terms_encoded_and look_ups
    look_up = []
    p_reps, p_lookup = pickle_load(cwd + "data/Encoding/passage.pt")
    retriever = BaseFaissIPRetriever(p_reps)
    shards = chain([(p_reps, p_lookup)])
    for p_reps, p_lookup in shards:
        retriever.add(p_reps)
        look_up += p_lookup
    model_w2v = KeyedVectors.load_word2vec_format('Model/PubMed-w2v.bin', binary=True)

    return mesh_dict, model, tokenizer, retriever, look_up, model_w2v


def search_queries(retriever, q_rep, lookup, depth):
    all_scores, all_indices = retriever.search(q_rep, depth)
    psg_indices = [[str(lookup[x]) for x in q_dd] for q_dd in all_indices]
    return psg_indices


def search_queries_multiple(retriever, q_reps, lookup, depth):
    returned_indices = []
    overall_psg_indices = {}
    for q_rep in q_reps:
        all_scores, all_indices = retriever.search(q_rep, 20)
        all_scores = all_scores[0]
        psg_indices = [str(lookup[x]) for x in all_indices[0]]
        min_score = min(all_scores)
        diff_score = max(all_scores) - min(all_scores)
        if diff_score == 0:
            for i, p in psg_indices:
                if psg_indices[i] not in overall_psg_indices:
                    overall_psg_indices[psg_indices[i]] = 0

        for i, s in enumerate(all_scores):
            if psg_indices[i] not in overall_psg_indices:
                overall_psg_indices[psg_indices[i]] = 0
            normalised_score = (all_scores[i] - min_score) / diff_score
            overall_psg_indices[psg_indices[i]] += normalised_score
    sorted_dict = sorted(overall_psg_indices.items(), key=lambda x: x[1], reverse=True)
    for sorted_item in sorted_dict[:depth]:
        returned_indices.append(sorted_item[0])

    return returned_indices


def seperate_keywords_group(keywords, model_w2v):
    keywords = [k.lower() for k in keywords]
    key_ids = []
    query_vectors = []
    keyword_groups = []
    for key_index, k in enumerate(keywords):
        model_incidence = [model_w2v[token] for token in tokenize(k) if token in model_w2v]
        if len(model_incidence) >= 1:
            add_vector = numpy.average(model_incidence, axis=0)
            a = numpy.sum(add_vector)
            if not numpy.isnan(a):
                query_vectors.append(add_vector)
                key_ids.append(key_index)
    if len(key_ids) > 1:
        pairs = {}
        for i in range(0, len(key_ids)):
            score = [s[0] for s in scipy.spatial.distance.cdist(query_vectors, [query_vectors[i]], 'cosine')]
            for s_index, s in enumerate(score):
                if (s <= 0.2) and (s_index > i):
                    if key_ids[i] in pairs:
                        pairs[key_ids[i]].append(key_ids[s_index])
                    else:
                        exist = False
                        for current_p in pairs:
                            current_values = pairs[current_p]
                            if (key_ids[i] in current_values) and (key_ids[s_index] in current_values):
                                exist = True
                                break
                            elif key_ids[i] in current_values:
                                pairs[current_p].append(key_ids[s_index])
                                exist = True
                                break
                            elif key_ids[s_index] in current_values:
                                pairs[current_p].append(key_ids[i])
                                exist = True
                                break
                        if not exist:
                            pairs[key_ids[i]] = [key_ids[s_index]]
        already_appeared = set()
        for p in pairs:
            local_pairs = [keywords[p]]
            already_appeared.add(p)
            for a_p in pairs[p]:
                already_appeared.add(a_p)
                local_pairs.append(keywords[a_p])
            keyword_groups.append(local_pairs)
        for id in key_ids:
            if id not in already_appeared:
                keyword_groups.append([keywords[id]])
    else:
        keyword_groups = [[k] for k in keywords]

    return keyword_groups


def keyword_suggestion_method(keyword, model, tokenizer, retriever, look_up):
    query = keyword.lower()
    query_tokenised = tokenizer.encode_plus(
        query,
        add_special_tokens=True,
        max_length=32,
        truncation=True,
        padding='max_length',
        return_token_type_ids=False,
        return_attention_mask=True,
        return_tensors='pt'
    )
    encoded = model(query_tokenised)
    uids = search_queries(retriever, encoded.q_reps.detach().numpy(), look_up, 30)
    return uids[0]


def semantic_suggestion_method(keywords, model, tokenizer, retriever, look_up):
    encoded = []
    for keyword in keywords:
        query = keyword.lower()
        query_tokenised = tokenizer.encode_plus(
            query,
            add_special_tokens=True,
            max_length=32,
            truncation=True,
            padding=False,
            return_token_type_ids=False,
            return_attention_mask=True,
            return_tensors='pt'
        )
        encoded.append(model(query_tokenised).q_reps.detach().numpy())
    if len(encoded) > 1:
        uids = [search_queries_multiple(retriever, encoded, look_up, 30)]
    else:
        uids = search_queries(retriever, encoded[0], look_up, 30)

    return uids[0]


def fragment_suggestion_method(keywords, model, tokenizer, retriever, look_up):
    encoded = []
    for keyword in keywords:
        query = keyword.lower()
        query_tokenised = tokenizer.encode_plus(
            query,
            add_special_tokens=True,
            max_length=32,
            truncation=True,
            padding='max_length',
            return_token_type_ids=False,
            return_attention_mask=True,
            return_tensors='pt'
        )
        encoded.append(model(query_tokenised).q_reps.detach().numpy())

    uids = [search_queries_multiple(retriever, encoded, look_up, 30)]
    return uids[0]


if __name__ == '__main__':
    mesh_dict, model, tokenizer, retriever, look_up, model_w2v = prepare_model()
    params = {
        'payload': {
            "Keywords": ["disease", "Heart attack", "medical condition", "blood test", "blood sample test"],
            "Type": "Semantic"
        },
        'mesh_dict': mesh_dict,
        'model': model,
        'tokenizer': tokenizer,
        'retriever': retriever,
        'look_up': look_up,
        'model_w2v': model_w2v
    }
    BERT_Suggest = Suggest_MeSH_Terms_With_BERT(params)
    print(BERT_Suggest.suggest())

import json
import numpy as np
import pandas as pd
import torch
import re
import string
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPTokenizer
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.multiclass import OneVsRestClassifier
from imblearn.under_sampling import RandomUnderSampler
from imblearn.pipeline import make_pipeline
from tabulate import tabulate


model_bert = SentenceTransformer('all-MiniLM-L6-v2')
model_clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
tokenizer = CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch32")

# Load data
print('Load data')
with open('data/filtered_data.json', 'r') as f:
    papers_data = json.load(f)

df = pd.DataFrame(papers_data)
df = df.dropna(how='any')
df = df.reset_index(drop=True)
print(f'Number of samples: {df.shape[1]}')

titles = df['paper_title'].tolist()
abstracts = df['abstract'].tolist()
readmes = df['github_readme_content'].tolist()
somef = df['somef_descriptions'].tolist()

print('Load data')
with open('data/filtered_data_complete.json', 'r') as f:
    papers_data_complete = json.load(f)
df_complete = pd.DataFrame(papers_data_complete)
print(f'Number of samples: {df.shape[1]}')
github_title = df_complete['github_repo_title'].tolist()
github_keywords = df_complete['github_keywords'].tolist()

github_title = df['github_repo_title'].tolist()
github_keywords = df['github_keywords'].tolist()

y = df['main_collection_area']
y_complete = df_complete['main_collection_area']
num_clusters = len(y.unique())


def preprocess_text(text):
    # Remove punctuation, numbers, and lower the text
    text = re.sub(f"[{string.punctuation}0-9]", " ", text.lower())
    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    text = " ".join([word for word in text.split() if word not in stop_words])
    return text


def compute_tfidf(text_list):
    # Preprocess each text in the list
    text_list = [preprocess_text(text) for text in text_list]
    
    # Define the TF-IDF vectorizer with tuning
    vectorizer = TfidfVectorizer(min_df=2, max_df=0.95, ngram_range=(1, 2), stop_words='english', max_features=3000)
    
    vectors = vectorizer.fit_transform(text_list)
    return vectors.toarray()

def compute_sentence_embeddings(text_list, batch_size=256):
    embeddings = []
    text_list = [text.strip() for text in text_list]

    for i in range(0, len(text_list), batch_size):
        print(i)
        batch = text_list[i:i + batch_size]
        batch_embeddings = model_bert.encode(batch)
        embeddings.append(batch_embeddings)

    # Concatenate all batch embeddings
    return np.vstack(embeddings)


def compute_clip_embeddings(text_list, batch_size=256):
    embeddings = []
    for i in range(0, len(text_list), batch_size):
        batch = text_list[i:i + batch_size]
        inputs = tokenizer(batch, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            batch_embeddings = model_clip.get_text_features(**inputs).cpu().numpy()
        embeddings.append(batch_embeddings)
    return np.vstack(embeddings)


def train_random_forest_with_undersampling(X, y, embedding_name, source_text):
    # Stratified K-Fold for cross-validation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Random undersampling for balancing classes
    #rus = RandomUnderSampler(sampling_strategy='not minority', random_state=42)

    # Create the RandomForest model
    base_rf = RandomForestClassifier(n_estimators=100, random_state=42)

    # One-vs-Rest Classifier with custom pipeline that applies undersampling
    clf = OneVsRestClassifier(
        make_pipeline(RandomUnderSampler(sampling_strategy='not minority', random_state=42), base_rf),
        verbose=2
    )
    
    accuracy_scores = []
    precision_scores = []
    recall_scores = []
    f1_scores = []

    # Cross-validation loop
    for train_index, test_index in skf.split(X, y):
        X_train, X_test = X[train_index], X[test_index]
        y_train, y_test = y[train_index], y[test_index]

        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)

        # Evaluation metrics
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted')
        recall = recall_score(y_test, y_pred, average='weighted')
        f1 = f1_score(y_test, y_pred, average='weighted')

        accuracy_scores.append(accuracy)
        precision_scores.append(precision)
        recall_scores.append(recall)
        f1_scores.append(f1)

        print(f'Fold Results for {embedding_name} (OvR Random Forest) - {source_text}:')
        print(classification_report(y_test, y_pred))
        print(f'Accuracy: {accuracy:.4f}, Precision: {precision:.4f}, Recall: {recall:.4f}, F1-Score: {f1:.4f}')
        print('-----------------------------------')

    # Average metrics over all folds
    print(f'Final Cross-Validated Results for {embedding_name} (OvR Random Forest) - {source_text}:')
    print(f'Average Accuracy: {sum(accuracy_scores)/len(accuracy_scores):.4f}')
    print(f'Average Precision: {sum(precision_scores)/len(precision_scores):.4f}')
    print(f'Average Recall: {sum(recall_scores)/len(recall_scores):.4f}')
    print(f'Average F1-Score: {sum(f1_scores)/len(f1_scores):.4f}')


def evaluate_clustering_metrics(X, y, embedding_name, source_text):
    print(f'Clustering metrics for {embedding_name} - {source_text}:')
    # Calculate metrics
    silhouette_avg = silhouette_score(X, y)
    calinski_harabasz = calinski_harabasz_score(X, y)
    davies_bouldin = davies_bouldin_score(X, y)
    
    # Return results in a dictionary
    metrics = {
        'Silhouette Score': silhouette_avg,
        'Calinski-Harabasz Index': calinski_harabasz,
        'Davies-Bouldin Index': davies_bouldin
    }
    
    table = [["Metric", "Score"]]
    for metric, score in metrics.items():
        table.append([metric, f"{score:.4f}"])
    
    print(f'Clustering metrics for {embedding_name} (OvR Random Forest) - {source_text}:')
    print(f'Silhouette Score: {silhouette_avg:.4f}')
    print(f'Calinski-Harabasz Index: {calinski_harabasz:.4f}')
    print(f'Davies-Bouldin Index: {davies_bouldin:.4f}')


print('Titles')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(titles)
    train_random_forest_with_undersampling(tfidf_embeddings, y, 'TF-IDF', 'Title')
    evaluate_clustering_metrics(tfidf_embeddings, y, 'TF-IDF', 'Title')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(titles)
    train_random_forest_with_undersampling(sentence_embeddings, y, 'Sentence Transformer', 'Title')
    evaluate_clustering_metrics(sentence_embeddings, y, 'Sentence Transformer', 'Title')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(titles)
    train_random_forest_with_undersampling(clip_embeddings, y, 'CLIP', 'Title')
    evaluate_clustering_metrics(clip_embeddings, y, 'CLIP', 'Title')


print('Abstract')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(abstracts)
    train_random_forest_with_undersampling(tfidf_embeddings, y, 'TF-IDF', 'Abstract')
    evaluate_clustering_metrics(tfidf_embeddings, y, 'TF-IDF', 'Abstract')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(abstracts)
    train_random_forest_with_undersampling(sentence_embeddings, y, 'Sentence Transformer', 'Abstract')
    evaluate_clustering_metrics(sentence_embeddings, y, 'Sentence Transformer', 'Abstract')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(abstracts)
    train_random_forest_with_undersampling(clip_embeddings, y, 'CLIP', 'Abstract')
    evaluate_clustering_metrics(clip_embeddings, y, 'CLIP', 'Abstract')


print('READMEs')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(readmes)
    train_random_forest_with_undersampling(tfidf_embeddings, y, 'TF-IDF', 'GitHub README Content')
    evaluate_clustering_metrics(tfidf_embeddings, y, 'TF-IDF', 'GitHub README Content')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(readmes)
    train_random_forest_with_undersampling(sentence_embeddings, y, 'Sentence Transformer', 'GitHub README Content')
    evaluate_clustering_metrics(sentence_embeddings, y, 'Sentence Transformer', 'GitHub README Content')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(readmes)
    train_random_forest_with_undersampling(clip_embeddings, y, 'CLIP', 'GitHub README Content')
    evaluate_clustering_metrics(clip_embeddings, y, 'CLIP', 'GitHub README Content')

print('Somef')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(somef)
    train_random_forest_with_undersampling(tfidf_embeddings, y, 'TF-IDF', 'SOMEF descriptions')
    evaluate_clustering_metrics(tfidf_embeddings, y, 'TF-IDF', 'SOMEF descriptions')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(somef)
    train_random_forest_with_undersampling(sentence_embeddings, y, 'Sentence Transformer', 'SOMEF descriptions')
    evaluate_clustering_metrics(sentence_embeddings, y, 'Sentence Transformer', 'SOMEF descriptions')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(somef)
    train_random_forest_with_undersampling(clip_embeddings, y, 'CLIP', 'SOMEF descriptions')
    evaluate_clustering_metrics(clip_embeddings, y, 'CLIP', 'SOMEF descriptions')
    
print('GitHub title')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(github_title)
    train_random_forest_with_undersampling(tfidf_embeddings, y_complete, 'TF-IDF', 'GitHub Title')
    evaluate_clustering_metrics(tfidf_embeddings, y_complete, 'TF-IDF', 'GitHub Title')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(github_title)
    train_random_forest_with_undersampling(sentence_embeddings, y_complete, 'Sentence Transformer', 'GitHub Title')
    evaluate_clustering_metrics(sentence_embeddings, y_complete, 'Sentence Transformer', 'GitHub Title')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(github_title)
    train_random_forest_with_undersampling(clip_embeddings, y_complete, 'CLIP', 'GitHub Title')
    evaluate_clustering_metrics(clip_embeddings, y_complete, 'CLIP', 'GitHub Title')
    
print('GitHub keywords')

if True:
    # TF-IDF Embeddings
    print('Computing TF-IDF embeddings')
    tfidf_embeddings = compute_tfidf(github_keywords)
    train_random_forest_with_undersampling(tfidf_embeddings, y_complete, 'TF-IDF', 'GitHub Keywords')
    evaluate_clustering_metrics(tfidf_embeddings, y_complete, 'TF-IDF', 'GitHub Keywords')

    # Sentence Transformer (BERT) Embeddings
    print('Computing Sentence Transformer embeddings')
    sentence_embeddings = compute_sentence_embeddings(github_keywords)
    train_random_forest_with_undersampling(sentence_embeddings, y_complete, 'Sentence Transformer', 'GitHub Keywords')
    evaluate_clustering_metrics(sentence_embeddings, y_complete, 'Sentence Transformer', 'GitHub Keywords')

    # CLIP Embeddings
    print('Computing CLIP embeddings')
    clip_embeddings = compute_clip_embeddings(github_keywords)
    train_random_forest_with_undersampling(clip_embeddings, y_complete, 'CLIP', 'GitHub Keywords')
    evaluate_clustering_metrics(clip_embeddings, y_complete, 'CLIP', 'GitHub Keywords')

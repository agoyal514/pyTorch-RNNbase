import numpy as np
import re
import codecs
import json
import torch
import random
import time
import sys


####################################################################################
####################################################################################
#############                                                    ###################
#############       make data set scaling unbalanced or not      ###################
#############                                                    ###################
####################################################################################
####################################################################################

def load_json(json_path):
    data_from_json = []
    for line in codecs.open(json_path, 'rb'):
        data_from_json.append(json.loads(line))

    if len(data_from_json) < 200000:
        data = make_data(data_from_json)
    else:
        data = make_data_scaling(data_from_json)

    return data



# positive_labels = [[0, 1] for _ in positive_examples]
# negative_labels = [[1, 0] for _ in negative_examples]
def make_data(data_from_json):
    x_text = []
    y = []
    for i, x in enumerate(data_from_json):
        if x['overall'] != 3.:
            x_text.append(x['reviewText'])
            if x['overall'] == 1. or x['overall'] == 2. :
                y_tmp = [1, 0]
                y.append(y_tmp)
            elif x['overall'] == 4. or x['overall'] == 5.:
                y_tmp = [0, 1]
                y.append(y_tmp)
    return [x_text, y]


def make_data_scaling(data_from_json):
    neg_num = 0
    for i, x in enumerate(data_from_json):
        if x['overall'] == 1. or x['overall'] == 2.:
            neg_num += 1
    return scaling_data(data_from_json, neg_num)


def scaling_data(data_from_json, neg_num):
    x_pos = []
    y_pos = []
    x_neg = []
    y_neg = []
    x_text = []
    y = []
    if neg_num < 100000:
        pos_num = 200000 - neg_num
        for i, x in enumerate(data_from_json):
            if x['overall'] != 3.:
                if x['overall'] == 1. or x['overall'] == 2.:
                    x_neg.append(x['reviewText'])
                    y_tmp = [1, 0]
                    y_neg.append(y_tmp)
                elif x['overall'] == 4. or x['overall'] == 5.:
                    x_pos.append(x['reviewText'])
                    y_tmp = [0, 1]
                    y_pos.append(y_tmp)

        shuffle_indices = np.random.permutation(np.arange(pos_num))
        new_x_pos = cut_list(x_pos, shuffle_indices)
        new_y_pos = cut_list(y_pos, shuffle_indices)

        x_text.extend(new_x_pos)
        x_text.extend(x_neg)

        y.extend(new_y_pos)
        y.extend(y_neg)
    else:
        num = 100000
        for i, x in enumerate(data_from_json):
            if x['overall'] != 3.:
                if x['overall'] == 1. or x['overall'] == 2.:
                    x_neg.append(x['reviewText'])
                    y_tmp = [1, 0]
                    y_neg.append(y_tmp)
                elif x['overall'] == 4. or x['overall'] == 5.:
                    x_pos.append(x['reviewText'])
                    y_tmp = [0, 1]
                    y_pos.append(y_tmp)
        shuffle_indices = np.random.permutation(np.arange(num))
        new_x_pos = cut_list(x_pos, shuffle_indices)
        new_y_pos = cut_list(y_pos, shuffle_indices)

        shuffle_indices = np.random.permutation(np.arange(num))
        new_x_neg = cut_list(x_neg, shuffle_indices)
        new_y_neg = cut_list(y_neg, shuffle_indices)

        x_text.extend(new_x_pos)
        x_text.extend(new_x_neg)

        y.extend(new_y_pos)
        y.extend(new_y_neg)
    return [x_text, y]



def cut_list(_list, indices):
    shuffled = []
    for idx in indices:
        shuffled.append(_list[idx])
    return shuffled


####################################################################################
####################################################################################
#############                                                    ###################
#############                     basic tokenizer                ###################
#############                                                    ###################
####################################################################################
####################################################################################


def clean_str(string):
    """
    Tokenization/string cleaning for all datasets except for SST.
    Original taken from https://github.com/yoonkim/CNN_sentence/blob/master/process_data.py
    """
    string = re.sub(r"[^A-Za-z0-9(),!?\'\`]", " ", string)
    string = re.sub(r"\'s", " \'s", string)
    string = re.sub(r"\'ve", " \'ve", string)
    string = re.sub(r"n\'t", " n\'t", string)
    string = re.sub(r"\'re", " \'re", string)
    string = re.sub(r"\'d", " \'d", string)
    string = re.sub(r"\'ll", " \'ll", string)
    string = re.sub(r",", " , ", string)
    string = re.sub(r"!", " ! ", string)
    string = re.sub(r"\(", " \( ", string)
    string = re.sub(r"\)", " \) ", string)
    string = re.sub(r"\?", " \? ", string)
    string = re.sub(r"\s{2,}", " ", string)
    return string.strip().lower()


####################################################################################
####################################################################################
#############                                                    ###################
#############     calculate max length of tokenized sentence     ###################
#############                                                    ###################
####################################################################################
####################################################################################

def max_len(sentence_list):
    sen_len = np.empty((1,len(sentence_list)), int)
    for i, x in enumerate(sentence_list):
        clean_sen = clean_str(x)
        word_list = clean_sen.split(" ")
        sen_len[0][i] = len(word_list)
    return np.max(list(sen_len.flat)), list(sen_len.flat)


def median_len(sentence_list):
    sen_len = np.empty((1,len(sentence_list)), int)
    for i, x in enumerate(sentence_list):
        clean_sen = clean_str(x)
        word_list = clean_sen.split(" ")
        sen_len[0][i] = len(word_list)
    return int(np.median(list(sen_len.flat))), list(sen_len.flat)



####################################################################################
####################################################################################
#############                                                    ###################
#############                    For mini-Batch                  ###################
#############                                                    ###################
####################################################################################
####################################################################################
def batch_iter(data, batch_size, num_epochs, seq_len, shuffle=True):
    """
    Generates a batch iterator for a dataset.
    """
    shuffled_data = []
    shuffled_len = []
    data_size = len(data)
    pos = []
    neg = []
    for i, x in enumerate(data):
        if x[1][0] == 0:
            pos.append(x)
        else:
            neg.append(x)
    num_batches_per_epoch = int((len(data)-1)/batch_size) + 1
    for epoch in range(10):
        # Shuffle the data at each epoch
        if shuffle:
            for batch_num in range(num_batches_per_epoch):
                random_pos_index = np.random.choice(len(pos), int(batch_size / 2))
                random_neg_index = np.random.choice(len(neg), int(batch_size / 2))
                for i, x in enumerate(random_neg_index):
                    shuffled_data.append(neg[x])
                    shuffled_len.append(seq_len[x])
                for i, x in enumerate(random_pos_index):
                    shuffled_data.append(pos[x])
                    shuffled_len.append(seq_len[x])
        else:
            shuffled_data = data
        for batch_num in range(num_batches_per_epoch):
            start_index = batch_num * batch_size
            end_index = min((batch_num + 1) * batch_size, data_size)
            yield [shuffled_data[start_index:end_index], shuffled_len[start_index:end_index]]


def tensor4batch(data_x, data_y, args):
    tensor4x = torch.zeros(len(data_x), int(args.seq_len)).type(torch.LongTensor)
    for i, x in enumerate(data_x):
        scalar_list = []
        for word in x:
            scalar = int(word)
            scalar_list.append(scalar)
        tensor4x[i] = torch.LongTensor(scalar_list)
    tensor4y = torch.zeros(len(data_y), args.num_classes).type(torch.FloatTensor)
    for i, y in enumerate(data_y):
        tensor4y[i] = torch.LongTensor(y.tolist())
    return tensor4x, tensor4y

####################################################################################
####################################################################################
#############                                                    ###################
#############        convert word to index and fill zeros        ###################
#############                                                    ###################
####################################################################################
####################################################################################

def word2idx_array(sentence_list, length):
    word_to_idx = {}
    idx_array = np.zeros((len(sentence_list), length))
    count = 0
    start = time.time()
    for i, x in enumerate(sentence_list):
        idx_tmp = np.empty((0,1), int)
        clean_sen = clean_str(x)
        word_list = clean_sen.split(" ")

        for word in word_list:
            if word not in word_to_idx:
                word_to_idx[word] = len(word_to_idx) + 1  # +1 to leave out zero for padding
            idx_tmp = np.vstack((idx_tmp,int(word_to_idx[word])))

        if length > len(idx_tmp):
            num_zeros = length - len(idx_tmp)
            zeros_array = np.zeros((1, num_zeros))
            sen_max_len = np.hstack((idx_tmp.T, zeros_array))
            idx_array[i] = sen_max_len
        else:
            idx_array[i] = idx_tmp[:length].T




        count += 1
        if count % 1000 == 0:
            end = time.time()
            sys.stdout.write(
                "\rI'm working at word2idx FN %({}/{}, {})".format(count,
                                                               len(sentence_list),
                                                                   end-start))
            start = end
    return idx_array, word_to_idx

def sorting_sequence(x_data, y_data, sequence):
    sorted_x = []
    sorted_y = []
    sorted_seq = []
    index = [i[0] for i in sorted(enumerate(sequence), key=lambda x: x[1])]
    index.reverse()
    for i, x in enumerate(index):
        sorted_x.append(x_data[x])
        sorted_y.append(y_data[x])
        sorted_seq.append(sequence[x])
    return [sorted_x, sorted_y, sorted_seq]
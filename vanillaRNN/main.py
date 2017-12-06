import sys
import os
import math
import time
import torch
import argparse
import datetime
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from vanillaRNN import data_helpers
from vanillaRNN.model import RNN
from vanillaRNN.build_dataset import Databuilder
from sklearn.metrics import confusion_matrix, auc, roc_curve

parser = argparse.ArgumentParser(description='Vanilla RNN')

# Model Hyperparameters
parser.add_argument('-lr', type=float, default=1e-2, help='setting learning rate')
parser.add_argument('-lr-decay', type=list,  default=[], help='Empty list for learning rate decay')
parser.add_argument('-hidden-size', type=int, default=128, help='setting hidden size [default : 128]')
parser.add_argument('-embed-dim', type=int, default=128, help='number of embedding dimension [default: 128]')
parser.add_argument('-num-layers', type=int, default=2, help='setting number of layers [default : 1]')

# Training parameters
parser.add_argument('-batch-size', type=int, default=512, help='batch size for training [default: 64]')
parser.add_argument('-num-epochs', type=int, default=100, help='number of epochs for train [default: 200]')
parser.add_argument('-dev-interval', type=int, default=1000, help='how many steps to wait before testing [default: 100]')
parser.add_argument('-save-interval', type=int, default=500, help='how many steps to wait before saving [default:500]')
parser.add_argument('-log-interval',  type=int, default=1,   help='how many steps to wait before logging training status [default: 1]')
parser.add_argument('-static', action='store_true', default=False, help='fix the embedding')
parser.add_argument('-list4ES', type=list,  default=[], help='Empty list for appending dev-acc')
parser.add_argument('-corrects-index', type=list,  default=[], help='Empty list for appending dev-acc')


# Data Set
parser.add_argument('-json-path', type=str, default="./data/amazon/Clothing_Shoes_and_Jewelry_5.json", help='Data source')
parser.add_argument('-vocab-size', type=int, default=0 , help='Vocab size')
parser.add_argument('-max-len', type=int, default=0 , help='max length among all of sentences')
parser.add_argument('-data-size', type=int, default=0, help='Data size')
parser.add_argument('-num-classes', type=int, default=2, help='Number of classes')
parser.add_argument('-trn-sample-percentage', type=float, default=.5, help='Percentage of the data to use for training')
parser.add_argument('-dev-sample-percentage', type=float, default=.2, help='Percentage of the data to use for validation')
parser.add_argument('-test-sample-percentage', type=float, default=.3, help='Percentage of the data to use for testing')
parser.add_argument('-seq-len', type=int, default=0, help='setting input size')
parser.add_argument('-class-num', type=int, default=2, help='class_num')

# saver
parser.add_argument('-iter', type=int, default=0, help='For checking iteration')
parser.add_argument('-save-dir', type=str, default='./RUNS/', help='Data size')
parser.add_argument('-final-model-dir', type=str, default='./Final_model/', help='Dir to saving learned model')
parser.add_argument('-snapshot', type=str, default='./RUNS/Final_model/', help='dir learned model')
parser.add_argument('-model-name', type=str, default='LSTM_word', help='Model name')
parser.add_argument('-data-name', type=str, default='Clothing_Shoes_and_Jewelry_5', help='Data name')

parser.add_argument('-dev-previous-auroc', type=float, default=.0, help='For saving best model')
parser.add_argument('-dev-current-auroc', type=float, default=.0, help='For saving best model')

args, unknown = parser.parse_known_args()
# Instantiate RNN model



print("Loading data...")
x_text, y = data_helpers.load_json(args.json_path)
max_len, seq_num = data_helpers.max_len(x_text)

x, vocab_dic = data_helpers.word2idx_array(x_text, max_len)
x = np.array(x)
y = np.array(y)
seq_num = np.array(seq_num)

# Randomly shuffle data
np.random.seed(int(time.time()))
shuffle_indices = np.random.permutation(np.arange(len(y)))
x_shuffled = x[shuffle_indices]
y_shuffled = y[shuffle_indices]
seq_num_shuffled = seq_num[shuffle_indices]

# Split train/test set
# TODO: This is very crude, should use cross-validation
trn_sample_index = -1 * int(args.trn_sample_percentage * float(len(y)))
test_sample_index = -1 * int(args.test_sample_percentage * float(len(y)))
x_train, x_dev, x_test = x_shuffled[:trn_sample_index], x_shuffled[trn_sample_index:test_sample_index], x_shuffled[test_sample_index:]
y_train, y_dev, y_test = y_shuffled[:trn_sample_index], y_shuffled[trn_sample_index:test_sample_index], y_shuffled[test_sample_index:]
seq_train, seq_dev, seq_test = seq_num_shuffled[:trn_sample_index], seq_num_shuffled[trn_sample_index:test_sample_index], seq_num_shuffled[test_sample_index:]
print("Vocabulary Size: {:d}".format(len(vocab_dic)))
print("Train/Dev split: {:d}/{:d}/{:d}".format(len(y_train), len(y_dev), len(y_test)))

# update args and print
args.embed_num = len(vocab_dic)
args.seq_len = int(max_len)
args.save_dir = os.path.join(args.save_dir, datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
args.snapshot = os.path.join(args.snapshot, '{}_{}.{}'.format(args.model_name, args.data_name,'pt'))

print("\nParameters:")
for attr, value in sorted(args.__dict__.items()):
    print("\t{}={}".format(attr.upper(), value))


# Make dataset
train_dataset = Databuilder(sen=x_train,
                            target=y_train,
                            args=args,
                            seq=seq_train)

dev_dataset = Databuilder(sen=x_dev,
                          target=y_dev,
                          args=args,
                          seq=seq_dev)

test_dataset = Databuilder(sen=x_test,
                           target=y_test,
                           args=args,
                           seq=seq_test)

# Make balanced_sampler
weights = data_helpers.make_weights_for_balanced_classes(y_train, args.class_num)
weights = torch.DoubleTensor(weights)
sampler = torch.utils.data.sampler.WeightedRandomSampler(weights, len(weights))

# Make data_loader
train_loader = torch.utils.data.DataLoader(train_dataset,
                                           batch_size=args.batch_size,
                                           shuffle=False,
                                           collate_fn=data_helpers.default_collate,
                                           sampler=sampler)

dev_loader = torch.utils.data.DataLoader(dev_dataset,
                                         batch_size=args.batch_size,
                                         shuffle=False,
                                         collate_fn=data_helpers.default_collate)

test_loader = torch.utils.data.DataLoader(test_dataset,
                                          batch_size=args.batch_size,
                                          shuffle=False,
                                          collate_fn=data_helpers.default_collate)

model = RNN(args)
if torch.cuda.is_available():
    model.cuda()
    print("model will use GPU")



def train(epoch):
    model.train()
    optimizer = torch.optim.RMSprop(model.parameters(), lr=args.lr)

    for batch_idx, (data, target, seq) in enumerate(train_loader):
        data, target, seq = data_helpers.sorting_sequence(data, target, seq, args)
        data, target = Variable(data).cuda(), Variable(target).cuda()
        optimizer.zero_grad()

        logit = model(data, seq)
        
        # print(logit[0:6])

        loss = F.nll_loss(logit, torch.max(target, 1)[1])

        args.lr = data_helpers.lr_decay(loss, args)

        loss.backward()
        optimizer.step()

        args.iter += 1

        if args.iter % args.log_interval == 0:
            corrects_data = (torch.max(logit, 1)[1] == torch.max(target, 1)[1]).data
            corrects = corrects_data.sum()
            accuracy = 100.0 * corrects / len(target)
            sys.stdout.write(
                '\rTrn||Batch[{}] - loss: {:.6f}  acc: {:.4f}%({}/{})'.format(args.iter,
                                                                              loss.data[0],
                                                                              accuracy,
                                                                              corrects,
                                                                              len(target)))
        if args.iter % args.dev_interval == 0:
            dev(model)

        if args.iter % args.save_interval == 0:
            if not os.path.isdir(args.save_dir): os.makedirs(args.save_dir)
            save_prefix = os.path.join(args.save_dir, 'snapshot')
            save_path = '{}_steps{}.pt'.format(save_prefix, args.iter)
            torch.save(model, save_path)


def dev(_model):
    _model.eval()
    corrects_dev, avg_loss, iter_dev, avg_auc = 0, 0, 0, 0
    tn, fn, tp, fp = 0, 0, 0, 0
    AUROC_list, BCR_list = [], []

    index = 0

    print("")
    y_hat_list = []
    for data, target, seq in dev_loader:
        data, target, seq = data_helpers.sorting_sequence(data, target, seq, args)
        data, target = Variable(data, volatile=True).cuda(), Variable(target).cuda()

        logit = model(data, seq)
        iter_dev += 1

        loss = F.nll_loss(logit, torch.max(target, 1)[1], size_average=False)
        loss_tmp = loss.data.cpu().numpy()[0]

        corrects_data = (torch.max(logit, 1)[1] == torch.max(target, 1)[1]).data
        corrects = corrects_data.sum()
        accuracy = 100.0 * corrects / len(target)

        y_hat = torch.max(logit, 1)[1].data.cpu().tolist()
        y_hat_list.append(y_hat)
        y_true = torch.max(target, 1)[1].data.cpu().numpy()

        if np.isin(1, y_true):
            batch_fpr, batch_tpr, batch_thresholds = roc_curve(y_true, y_hat, pos_label=1)
            batch_tn, batch_fp, batch_fn, batch_tp = confusion_matrix(y_true, y_hat).ravel()
            batch_TPR = batch_tp / (batch_tp + batch_fn)
            batch_TNR = batch_tn / (batch_tn + batch_fp)
            batch_AUROC = auc(batch_fpr, batch_tpr)
            batch_BCR = math.sqrt(batch_TPR * batch_TNR)

            tn += batch_tn
            fp += batch_fp
            fn += batch_fn
            tp += batch_tp
            AUROC_list.append(batch_AUROC)
            BCR_list.append(batch_BCR)

            sys.stdout.write(
                '\rDev||Batch[{}] - loss: {:.6f}  acc: {:.4f}%({}/{}  TPR: {:.2f}  TNR: {:.2f}  AUROC: {:.2f}  BCR: {:.2f})'.
                    format(iter_dev,
                           loss.data[0],
                           accuracy,
                           corrects,
                           args.batch_size,
                           batch_TPR,
                           batch_TNR,
                           batch_AUROC,
                           batch_BCR
                           ))
            avg_loss += loss_tmp
            corrects_dev += corrects

        corrects_list = []
        for i, x in enumerate(corrects_data):
            index += 1
            if x == 1:
                corrects_list.append(index)

    args.corrects_index.extend(corrects_list)

    size = len(y_dev)
    avg_loss = avg_loss / iter_dev
    accuracy = 100.0 * corrects_dev / size
    TPR = tp / (tp + fn)
    TNR = tn / (tn + fp)
    AUROC = sum(AUROC_list[0:len(AUROC_list) - 1]) / len(AUROC_list)
    BCR = sum(BCR_list[0:len(BCR_list) - 1]) / len(BCR_list)

    print('\nDEV - loss: {:.6f}  acc: {:.4f}%({}/{}) TPR: {:.2f}  TNR: {:.2f}  AUROC: {:.2f}  BCR: {:.2f})'.
          format(avg_loss,
                 accuracy,
                 corrects_dev,
                 size,
                 TPR,
                 TNR,
                 AUROC,
                 BCR
                 ))
    args.list4ES.append(accuracy)

    args.dev_current_auroc = AUROC
    if args.dev_current_auroc > args.dev_previous_auroc:
        if not os.path.isdir(args.final_model_dir): os.makedirs(args.final_model_dir)
        save_prefix = os.path.join(args.final_model_dir, args.model_name)
        save_path = '{}_{}.pt'.format(save_prefix, args.data_name)
        torch.save(model, save_path)
        print("This model is the best model up to now")
    args.dev_previous_auroc = args.dev_current_auroc


def test(path):
    # cnn = torch.load('./RUNS/2017-12-04_03-43-01/snapshot_steps4000.pt')
    cnn = torch.load(args.snapshot)
    cnn.cuda()
    print("Test started")

    cnn.eval()
    corrects_test, avg_loss, iter_test, avg_auc = 0, 0, 0, 0
    tn, fn, tp, fp = 0, 0, 0, 0
    AUROC_list, BCR_list = [], []

    print("")
    for data, target, seq in dev_loader:
        data, target, seq = data_helpers.sorting_sequence(data, target, seq, args)
        data, target = Variable(data, volatile=True).cuda(), Variable(target).cuda()

        logit = cnn(data, seq)

        iter_test += 1

        loss = F.nll_loss(logit, torch.max(target, 1)[1], size_average=False)
        loss_tmp = loss.data.cpu().numpy()[0]
        corrects_data = (torch.max(logit, 1)[1] == torch.max(target, 1)[1]).data

        corrects = corrects_data.sum()
        accuracy = 100.0 * corrects / len(target)

        y_pred = torch.max(logit, 1)[1].data.cpu().numpy()
        y_true = torch.max(target, 1)[1].data.cpu().numpy()

        if np.isin(1, y_true):
            batch_fpr, batch_tpr, batch_thresholds = roc_curve(y_true, y_pred, pos_label=1)
            batch_tn, batch_fp, batch_fn, batch_tp = confusion_matrix(y_true, y_pred).ravel()
            batch_TPR = batch_tp / (batch_tp + batch_fn)
            batch_TNR = batch_tn / (batch_tn + batch_fp)
            batch_AUROC = auc(batch_fpr, batch_tpr)
            batch_BCR = math.sqrt(batch_TPR * batch_TNR)

            tn += batch_tn
            fp += batch_fp
            fn += batch_fn
            tp += batch_tp
            AUROC_list.append(batch_AUROC)
            BCR_list.append(batch_BCR)

            sys.stdout.write(
                '\rTEST||Batch[{}] - loss: {:.6f}  acc: {:.4f}%({}/{}  TPR: {:.2f}  TNR: {:.2f}  AUROC: {:.2f}  BCR: {:.2f})'.
                    format(iter_test,
                           loss.data[0],
                           accuracy,
                           corrects,
                           args.batch_size,
                           batch_TPR,
                           batch_TNR,
                           batch_AUROC,
                           batch_BCR
                           ))
            avg_loss += loss_tmp
            corrects_test += corrects

    size = len(y_test)
    avg_loss = avg_loss / iter_test
    accuracy = 100.0 * corrects_test / size
    TPR = tp / (tp + fn)
    TNR = tn / (tn + fp)
    AUROC = sum(AUROC_list[0:len(AUROC_list) - 1]) / len(AUROC_list)
    BCR = sum(BCR_list[0:len(BCR_list) - 1]) / len(BCR_list)

    print('\nTEST - loss: {:.6f}  acc: {:.4f}%({}/{}) TPR: {:.2f}  TNR: {:.2f}  AUROC: {:.2f}  BCR: {:.2f})'.
          format(avg_loss,
                 accuracy,
                 corrects_test,
                 size,
                 TPR,
                 TNR,
                 AUROC,
                 BCR
                 ))

    indicators = ['accuracy', 'TPR', 'TNR', 'AUROC', 'BCR']
    result_list = [accuracy, TPR, TNR, AUROC, BCR]

    import pandas as pd
    results = pd.DataFrame(result_list, columns=['{}_{}'.format(args.model_name, args.data_name)], index=indicators)
    save_path = '{}_{}.csv'.format(path, args.data_name)
    results.to_csv(save_path)


if __name__ == "__main__":
    for epoch in range(1,100):
        train(epoch)

        # if epoch % 30 == 0:
            # args.lr = args.lr * (0.1 ** (epoch // 30))
            # print('LR is set to {}'.format(args.lr))

    print("training is over")
    if not os.path.isdir(args.final_model_dir): os.makedirs(args.final_model_dir)
    save_prefix = os.path.join(args.final_model_dir, args.model_name)
    save_path = '{}_{}.pt'.format(save_prefix, args.data_name)
    torch.save(model, save_path)
    test(save_prefix)
else:
    print("fuck")

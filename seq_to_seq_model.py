# -*- coding: utf-8 -*-
"""seq_to_seq_definitivo.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1i04gDe7VwxezAtMZzGirvolutWuA7kn3

###**SEQ TO SEQ:**

This program is a Seq2Seq, short for Sequence-to-Sequence, quite qualified for predicting data based on time sequences.

Such a structure is composed by an encoder, which takes in the input sequence and encodes it into a fixed-size context vector, capturing the essential information from the input, and a decoder which uses the context vector generated by the Encoder to produce the output sequence, step by step.

Such a model learns to map a sequence into another one. Encoder and decoder are structured using LSTM layers.

**NOTE:**  Code is different from other algorithms of the project only for what regards the network and relative classes, hyperparameters and utilized data.
"""

import numpy as np
from math import sqrt
from torch.utils.data import DataLoader
import pandas as pd
import torch
import torch.nn as nn
from torch import optim
import os
import time
import pickle as pc
import typing
from hyperopt import fmin, tpe, hp, Trials, STATUS_OK
from functools import partial
from sklearn.preprocessing import StandardScaler, MinMaxScaler
import matplotlib.pyplot as plt
import math
import random
import torch.nn.functional as F
from torch.optim.lr_scheduler import ReduceLROnPlateau
import datetime
from datetime import datetime, timedelta
from torch.utils.data import Sampler


_author_ = 'Enrico Bignozzi','Emanuele Antonelli', 'Raffaello Mastromarino', 'Niko Brimi'
_credits_ = ["Enrico Bignozzi", "Emanuele Antonelli", "Raffaello Mastromarino", "Niko Brimi", "Paolo Scaccia", "Paolo Antonelli"]
_license_ = "GPL"
_version_ = "1.0"
_maintainer_ = "Paolo Scaccia <paolo.scaccia@adaptivemeteo.com>", "Emanuele Antonelli <emaantonelli20@gmail.com>","huygenssteiner971@gmail.com"
_email_      = "paolo.scaccia@adaptivemeteo.com", "emaantonelli20@gmail.com", "huygenssteiner971@gmail.com"









class SpecificIndicesSampler(Sampler):#questo serve al fine di fare il salto delle batches nelle quali abbiamo dei buchi
    def __init__(self, indices):
        self.indices = indices

    def __iter__(self):
        return iter(self.indices)

    def __len__(self):
        return len(self.indices)


class EarlyStopping:
    def __init__(self, patience=7, verbose=False, delta=0):
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = np.Inf
        self.delta = delta

    def __call__(self, val_loss, model, path):
        score = -val_loss
        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, model, path)
        elif score < self.best_score + self.delta:
            self.counter += 1
            print(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, model, path)
            self.counter = 0

    def save_checkpoint(self, val_loss, model, path):
        if self.verbose:
            print(f'Validation loss decreased ({self.val_loss_min:.6f} --> {val_loss:.6f}).  Saving model ...')
        torch.save(model.state_dict(), path + '/' + 'checkpoint.pth')
        self.val_loss_min = val_loss



def MAE(pred, true):
    return np.mean(np.abs(pred - true))


def MSE(pred, true):
    return np.mean((pred - true) ** 2)


def RMSE(pred, true):
    return np.sqrt(MSE(pred, true))


def MAPE(pred, true):
    return np.mean(np.abs((pred - true) / true))


def MSPE(pred, true):
    return np.mean(np.square((pred - true) / true))


import sys
import csv

# Check the number of arguments passed


csv_file = sys.argv[1]
len_to_predict = int(sys.argv[2])
feature_to_predict = sys.argv[3]
station_to_predict = sys.argv[4]
last_column = feature_to_predict + "_STA{}".format(station_to_predict)
print("You are predicting{}".format(last_column))
df = pd.read_csv(csv_file).dropna()#carico i dati in un dataframe
df['DATE'] = pd.to_datetime(df['DATE'])
df['hour']=df['DATE'].dt.hour
df['month']=df.DATE.dt.month
col0= ['DATE', 'TEMP_STA0', 'TEMP_STA1', 'TEMP_STA2', 'TEMP_STA3', 'TEMP_STA4', 'HUM_STA0',
       'HUM_STA1', 'HUM_STA2', 'HUM_STA3', "HUM_STA4", 'PRESS_STA0',
       'PRESS_STA1', 'PRESS_STA2', 'PRESS_STA3', 'PRESS_STA4', 'PRO_X_STA0',
       'PRO_X_STA1', 'PRO_X_STA2', 'PRO_X_STA3', 'PRO_X_STA4', 'PRO_Y_STA0',
       'PRO_Y_STA1', 'PRO_Y_STA2', 'PRO_Y_STA3', 'PRO_Y_STA4', 'hour', 'month']#seleziono le colonne relative alle features da utilizzare

df=df[col0]
df["PRED_COL"] = df[last_column]
df.drop(columns = last_column, inplace = True)
df.rename(columns={"PRED_COL": last_column}, inplace=True)
co = df.columns[1:]
df = df.reset_index(drop=True)
Dal momento che i dati dalle stazioni sono spesso mancanti e presentano diversi nan si è deciso di implementare un meccanismo di salto delle batch, che fa sì che le sequenze che costituiscono le batch siano costruite in maniera tale da non presentare discontinuità.
desired_interval = 1008               #Intervallo di tempo senza dati mancanti che vogliamo; deve essere maggiore o uguale a seq_len+pred_len
df["DATE"]=pd.to_datetime(df["DATE"])
desired_duration = timedelta(days=7)
good_starts = []
for i in range(df.shape[0]-desired_interval):                                      #Creo vettore di indici buoni per selezionare sequenze senza salti
  if df["DATE"][i+desired_interval]-df["DATE"][i] == desired_duration:
    good_starts.append(df.index[i])                                           #SE VUOI PREVEDERE IL VENTO VA COMMENTATA QUESTA RIGA
fea = df.shape[1]-1
good_starts_train = good_starts[0:int(len(good_starts)*0.8)]            #Divido il vettore good_starts in indici iniziali di train e di validation
good_starts_vali = good_starts[int(len(good_starts)*0.8):int(len(good_starts)*0.9)]
good_starts_vali = [l for l in good_starts_vali if l>(good_starts_train[-1]+desired_interval+1)]
good_starts_test = good_starts[int(len(good_starts)*0.9):int(1*len(good_starts))]
good_starts_test = [l for l in good_starts_test if l>(good_starts_vali[-1]+desired_interval+1)] #Non voglio che train e validation si sovrappongano

shuffled_list = good_starts_train.copy()                                                        #Mischio il train
random.shuffle(shuffled_list)
tr = shuffled_list                                                                     #Scelgo un tot di indici da cui iniziare per le batch di train e un tot per validation
va = good_starts_vali
te =  good_starts_test                                           #Visto che altrimenti il train impiegherebbe giorni
gs=[tr,va,te]                                                                                      #Nel dataloader.train selezionerò il primo array di indici per scegliere indici (gs[0])
df=df[:-1]
class Dataset():#'forecasting task, options:[M, S, MS]; M:multivariate predict multivariate, S:univariate predict univariate, MS:multivariate predict univariate')
    def __init__(self, root_path=None, flag='train', size=None,
                 features='MS',target=last_column, scale=True, timeenc=0, freq='10m'):

        # size [seq_len, label_len, pred_len]
        # info sugli input
        # size:lista contenente [seq_len, label_len, pred_len]
        # features: stringa che specifica il tipo di task di previsione
        # target: stringa che specifica la variabile target
        # scale: se True si effettua lo scaling dei dati con MinMax Scaler, altrimenti False
        # timeenc: intero indicante il tipo di encoding temporale
        # freq: stringa che specifica la frequenza
        if size == None:
            print("size è none. Forse ci sono problemi")
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        # init
        assert flag in ['train', 'val','test']
        type_map = {'train': 0, 'val': 1, 'test':2}#flag che specifica il tipo di splitting diverso per ogni set
        self.set_type = type_map[flag]

        self.features = features
        self.target = target
        self.scale = scale
        self.timeenc = timeenc
        self.freq = freq
        self.root_path = root_path
        self.__read_data__()

    def __read_data__(self):#questo metodo effettua una lettura e un preprocessing dei dati
        self.scaler =MinMaxScaler()#scaler che normalizza i dati tra 0 e 1
        df_raw = df
        #border1s e border2s sono liste usate per definire gli estremi degli intervalli sulla base del tipo di splitting
        border1s = [0,
                    0,
                    0]
        border2s = [int(len(df_raw)*1),
                    int(len(df_raw)*1),
                    int(len(df_raw)*1)]
                    #teoricamente se non ci fosse il salto di batch,
                    #border1s[0]=0,border2s[0]=int(len(df_raw))*0.7 per prendere il 70% del dataset in train, e via cosi' con gli altri elementi per validation e test
        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]
        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]

        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        if self.scale:
            stop_index = good_starts_train[-1]+desired_interval
            train_data = df_data.iloc[:stop_index + 1]
            self.scaler.fit(train_data.values)
            data = self.scaler.transform(df_data.values)
            self.scaler.fit(train_data[self.target].values.reshape(-1, 1))#cosi' poi da andare a denormalizzare le previsioni
        else:
            data = df_data.values
        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        df_stamp = df_raw[['DATE']][border1:border2]
        df_stamp['DATE'] = pd.to_datetime(df_stamp.DATE)
        #df_stamp['DATE'] = pd.to_datetime(df_stamp.Date)

        df_stamp['month'] = df_stamp.DATE.apply(lambda row: row.month, 1)
        df_stamp['minute'] = df_stamp.DATE.apply(lambda row: row.minute, 10)
        df_stamp['hour'] = df_stamp.DATE.apply(lambda row: row.hour, 1)
        data_stamp = df_stamp.drop(labels=['DATE'], axis=1).values


        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        self.data_stamp = data_stamp


    def __getitem__(self, index):#questo metodo è usato per recuperare una specifica sequenza di dati dal dataset dato un certo indice
        s_begin = index
        s_end = s_begin + self.seq_len
        seq_x = self.data_x[s_begin:s_end]
        seq_y = self.data_y[s_begin:s_end+self.pred_len]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        return seq_x,seq_x_mark,seq_y

    def __len__(self):#ritorna il numero totale di sequenze nel dataset
        return len(self.data_x) - self.seq_len - self.pred_len + 1

    def inverse_transform(self, data):# effettua lo scaling inverso dei dati nel caso si sia scelto di riscalarli nel preprocessing
        return self.scaler.inverse_transform(data)

from torch.autograd import Variable
device='cuda'
class Encoder(nn.Module):#l'encoder prende in input i dati e ne crea
                          #una nuova rappresentazione
    def __init__(self, seq_len, n_features, embedding_dim):
        super(Encoder, self).__init__()

        self.seq_len, self.n_features = seq_len, n_features
        self.embedding_dim, self.hidden_dim = embedding_dim,  embedding_dim
        self.num_layers = 1
        self.rnn1 = nn.LSTM(
          input_size=n_features,
          hidden_size=self.hidden_dim,
          num_layers=1,
          batch_first=True,
          dropout = 0
        )#l'encoder è costruito a partire da una cella lstm

    def forward(self, x):

        x = x.reshape((64, self.seq_len, self.n_features))#(batch, seq, features)

        h_1 = Variable(torch.zeros(
            self.num_layers, x.size(0), self.hidden_dim).to(device))#inizializzo l'hidden della LSTM con un vettore di zeri


        c_1 = Variable(torch.zeros(
            self.num_layers, x.size(0), self.hidden_dim).to(device))#inizializzo il cell della LSTM con un vettore di zeri

        x, (hidden, cell) = self.rnn1(x,(h_1, c_1))#h1=hidden_cell,l'output
        #del passo temporale precedente viene utilizzato come stato nascosto per il passo temporale corrente.
        #c1 (cell state): Questo è specifico per le LSTM. È lo stato della cella di memoria della LSTM all'istante temporale corrente

        return x, hidden , cell#la nuova rappresentazione dei dati generata dall'encoder è codificata nell'hidden e il cell dell'LSTM, ovvero la short e la long term memory

class Decoder(nn.Module):#il decoder viene utilizzato per sfruttare la rappresentazione degli input generata dall'encoder al fine di generare gli output
    def __init__(self, seq_len, input_dim, n_features):
        super(Decoder, self).__init__()

        self.seq_len, self.input_dim = seq_len, input_dim
        self.hidden_dim, self.n_features =  input_dim, n_features

        self.rnn1 = nn.LSTM(
          input_size=n_features,
          hidden_size=input_dim,
          num_layers=1,
          batch_first=True,
          dropout = 0
        )

        self.output_layer = nn.Linear(self.hidden_dim, n_features)
    def forward(self, x,input_hidden,input_cell):

        x, (hidden_n, cell_n) = self.rnn1(x,(input_hidden,input_cell))#viene inizializzata una LSTM con l'hidden e il cell uscenti
        #dalla LSTM dell'encoder e produce un output in una dimensione latente

        x = self.output_layer(x)#l'output della LSTM è mandato in input a un linear che produce un tensore
        #nello spazio delle feature da prevedere e quindi il nostro output
        return x, hidden_n, cell_n#ritorna l'output, l'hidden e il cell finali del decoder che verranno nuovamente
        #passati al decoder al fine di produrre iterativamente gli output





class Model(nn.Module):#mettiamo insieme i pezzi per costruire il nostro modello
    def __init__(self,batch_size, pred_len,seq_len, n_features,  dropout, nlayers,hidden):
        super(Model, self).__init__()

        embedding_dim=hidden
        self.encoder = Encoder(seq_len, n_features, embedding_dim).to(device)
        self.output_length = pred_len
        self.decoder = Decoder(seq_len, embedding_dim, n_features).to(device)


    def forward(self,x):
        encoder_output,hidden,cell = self.encoder(x)#l'encoder genera la nuova rappresentazione degli input
        #prev_output become the next input to the LSTM cell
        prev_output = x[:,-1:,:]
        for out_days in range(self.output_length) :#uso il for per produrre autoregressivamente gli output,
        #passando di volta in volta gli output prodotti e inizializzando
        #il decoder con l'hidden e il cell al passo precedente per produrre l'output successivo.
        #Questo va iterato per un numero di passi differenti a seconda della lunghezza della previsione che si ha intenzione di produrre.
            prev_x,prev_hidden,prev_cell = self.decoder(prev_output,hidden,cell)
            hidden,cell = prev_hidden,prev_cell
            prev_output = prev_x[:,-1:,:]
        return prev_x[:,-1:,:]#ritorniamo l'ultimo degli output prodotti, corrispondente alla nostra previsione.


class DNNModel(object):
    def __init__(self,batch_size,seq_len,lstm_units,lr,nlayers, dropout, pred_len = len_to_predict, epochs_early_stopping=20):
        self.embed='fixed'
        self.batch_size=64#batch_size
        self.freq='10m'
        self.num_workers=0
        self.pred_len=pred_len
        self.label_len=6
        self.seq_len=seq_len
        self.n_features=4
        self.lstm_units=lstm_units
        self.train_epochs=500
        self.features='MS'
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.checkpoints='./checkpoints/'
        self.lr=lr
        self.nlayers=nlayers
        self.dropout=dropout
        self.model = self._build_model()

    def data_provider(self,flag):
        data_dict = {'ETTh1': Dataset}
        Data = data_dict['ETTh1']
        timeenc = 0 if self.embed == 'timeF' else 1
        if flag == 'val':
            shuffle_flag = False
            drop_last =  True
            batch_size =  1
            freq = self.freq
            v_s = 1

        elif flag == 'test':
            shuffle_flag = False
            drop_last =  True
            batch_size =  1
            freq = self.freq
            v_s = 2

        else:
            shuffle_flag= False
            drop_last =  True
            batch_size =self.batch_size
            freq = self.freq
            v_s = 0

        data_set = Data(
            flag=flag,
            size=[self.seq_len, self.label_len,self.pred_len],
            freq=self.freq
        )
        #print(flag, len(data_set))
        data_loader = DataLoader(
            data_set,
            batch_size=self.batch_size,
            shuffle=shuffle_flag,
            num_workers=self.num_workers,
            drop_last=drop_last,
            sampler=SpecificIndicesSampler(gs[v_s])#Sampler accede al vettore di indici buoni che ho definito (o train o validation) e sceglie indici da li cosi da non avere salti
            )                                      #in una singola sequenza. Non si può mettere Sampler e shuffle insieme, quindi lo shuffle è effettuato prima
        return data_set, data_loader

    def _build_model(self):
        model = Model(seq_len=self.seq_len,pred_len=self.pred_len,n_features=self.n_features,batch_size=self.batch_size, hidden=self.lstm_units,nlayers=self.nlayers,dropout=self.dropout).to("cuda")
        return model

    def _select_optimizer(self):
        model_optim = optim.Adam(self.model.parameters(), lr=self.lr)
        return model_optim

    def _select_criterion(self):
        criterion = nn.MSELoss()#nn.HuberLoss(reduction='mean', delta=1.0)#nn.MSELoss()
        return criterion

    def _get_data(self, flag):
        data_set, data_loader = self.data_provider(flag)
        return data_set, data_loader

    def vali(self, vali_data, vali_loader, criterion):#si usa per il dataset di validation e di test
        total_loss = []
        self.model.eval()
        with torch.no_grad():
          for i, (batch_x,batch_x_mark,batch_y) in enumerate(vali_loader):
            batch_x = batch_x.float().to(self.device)
            batch_y = batch_y.float().to(self.device)
            outputs = self.model(batch_x)
            f_dim = -1 if(self.features == 'MS' or self.features =='S')  else 0
            outputs = outputs[:, -1:, f_dim:]#prendo ultimo elemento predetto
            batch_y = batch_y[:, -1:, f_dim:].to(self.device)#prendo ultimo valore della sequenza, vale a dire quello che si vuole prevedere
            pred = outputs.detach().cpu()
            true = batch_y.detach().cpu()
            loss = criterion(pred, true)

            total_loss.append(loss)

        total_loss = np.average(total_loss)
        self.model.train()
        return total_loss

    def train(self,setting):#con questo metodo si addestra il modello
        train_data, train_loader = self._get_data(flag='train')
        vali_data, vali_loader = self._get_data(flag='val')
        test_data, test_loader = self._get_data(flag='test')
        train_loss_graph = []
        vali_loss_graph = []

        path = os.path.join(self.checkpoints, setting)
        if not os.path.exists(path):
            os.makedirs(path)
        time_now = time.time()
        train_steps = len(train_loader)
        early_stopping = EarlyStopping(patience=10, verbose=True)
        model_optim = self._select_optimizer()
        criterion = self._select_criterion()
        scheduler = ReduceLROnPlateau(model_optim, mode='min', patience=3, factor=0.5, verbose=False)#lo scheduler riduce il learning rate se non vi sono miglioramenti della loss per un numero di step uguale al patience
        for epoch in range(self.train_epochs):
            iter_count = 0
            train_loss = []
            self.model.train()
            epoch_time = time.time()
            for i, (batch_x,batch_x_mark, batch_y) in enumerate(train_loader):
                iter_count += 1
                model_optim.zero_grad()
                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)
                outputs = self.model(batch_x)
                f_dim = -1 if(self.features == 'MS' or self.features =='S')  else 0
                outputs = outputs[:, -1:, f_dim:]
                batch_y = batch_y[:, -1:, f_dim:].to(self.device)
                loss = criterion(outputs, batch_y)
                train_loss.append(loss.item())

                if (i + 1) % 10000 == 0:
                    print("\titers: {0}, epoch: {1} | loss: {2:.7f}".format(i + 1, epoch + 1, loss.item()))
                    speed = (time.time() - time_now) / iter_count
                    left_time = speed * ((self.train_epochs - epoch) * train_steps - i)
                    print('\tspeed: {:.4f}s/iter; left time: {:.4f}s'.format(speed, left_time))
                    iter_count = 0
                    time_now = time.time()

                loss.backward()
                model_optim.step()

            print("Epoch: {} cost time: {}".format(epoch + 1, time.time() - epoch_time))
            train_loss = np.average(train_loss)
            vali_loss= self.vali(vali_data, vali_loader, criterion)
            scheduler.step(vali_loss)
            test_loss = self.vali(test_data, test_loader, criterion)

            print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f} Vali Loss: {3:.7f} Test Loss: {4:.7f}".format(
                epoch + 1, train_steps, train_loss, vali_loss, test_loss))

            early_stopping(vali_loss, self.model, path)
            if early_stopping.early_stop:
                print("Early stopping")
                break
        train_loss_graph.append(train_loss)
        vali_loss_graph.append(vali_loss)

        best_model_path = path + '/' + 'checkpoint.pth'
        self.model.load_state_dict(torch.load(best_model_path))

        plt.plot(range(len(train_loss_graph)), train_loss_graph, label="train")
        plt.plot(range(len(vali_loss_graph)), vali_loss_graph, label="validation")
        print("train:", len(train_loss_graph))
        print("vali:", len(vali_loss_graph))
        plt.legend()
        plt.show()
        best_model_path = path + '/' + 'checkpoint.pth'
        self.model.load_state_dict(torch.load(best_model_path))


        return self.model




    def vali_test(self, setting, test=True):#questo serve dopo per testare le prestazioni del miglior modello sul dataset di test
        test_data, test_loader = self._get_data(flag='test')

        if test:
            print('loading model')
            self.model.load_state_dict(torch.load(os.path.join('./checkpoints/' + setting, 'checkpoint.pth')))

        preds = []
        trues = []
        folder_path = './test_results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        self.model.eval()
        with torch.no_grad():
            for i, (batch_x,batch_x_mark, batch_y) in enumerate(test_loader):
              batch_x = batch_x.float().to(self.device)
              batch_y = batch_y.float().to(self.device)
              outputs = self.model(batch_x)
              f_dim = -1 if(self.features == 'MS' or self.features =='S')  else 0
              outputs = outputs[:, -1:, f_dim:]
              batch_y = batch_y[:, -1:, f_dim:].to(self.device)
              outputs = outputs.detach().cpu().numpy()
              batch_y = batch_y.detach().cpu().numpy()
              pred = outputs  # outputs.detach().cpu().numpy()  # .squeeze()
              true = batch_y  # batch_y.detach().cpu().numpy()  # .squeeze()
              preds.append(pred)
              trues.append(true)


        preds = np.array(preds)
        trues = np.array(trues)
        #print('test shape:', preds.shape, trues.shape)
        preds = preds.reshape(-1, preds.shape[-2], preds.shape[-1])
        trues = trues.reshape(-1, trues.shape[-2], trues.shape[-1])
        #print('test shape:', preds.shape, trues.shape)

        # result save
        folder_path = './results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        return preds,trues
def _build_space():#la funzione genera lo spazio di ricerca per gli iperaparametri da usare nel fine-tuning
    space = {
        'batch_size': hp.quniform('batch_size', 16, 526, 16),
        'seq_len': hp.quniform('seq_len', 10, 300, 1),
        'lstm_units': hp.quniform('lstm_units', 2, 300, 2),
        'lr': hp.uniform('lr', 0.001, 0.01),
        'nlayers': 1,#hp.quniform('nlayers', 1, 2, 1),
        'dropout': hp.uniform('dropout', 0, 0.3),
        }
    return space



def _hyperopt_objective(hyperparameters, trials, trials_file_path, max_evals):#definisce l'obiettivo della minimizzazione per il processo di ottimizzazione degli iperparametri
    #info input:
    #hyperparameters: dizionario contenente gli iperparametri da valutare
    #trials:oggetto che conserva le informazioni rilevanti per il processo di ottimizzazione
    #trials_file_path: path del file in cui salvare i trials
    #max_evals: numero di valutazioni massimo della funzione di costo
    pc.dump(trials, open(trials_file_path, "wb"))
    setting = '{}'.format('EMANUELE')
    print(hyperparameters)
    forecaster = DNNModel(batch_size=int(hyperparameters['batch_size']),seq_len=int(hyperparameters['seq_len']),lstm_units=int(hyperparameters['lstm_units']),nlayers=int(hyperparameters['nlayers']),lr=(hyperparameters['lr']),dropout=(hyperparameters['dropout']))

    forecaster.train(setting).to("cuda")
    Yp_mean ,Y_test= forecaster.vali_test(setting,test=True)
    Y_test = Dataset(flag='test',size=[1,1,1],freq='10m').inverse_transform(Y_test.reshape(-1, Y_test.shape[-1])).flatten()
    Yp_mean = Dataset(flag='test',size=[1,1,1],freq='10m').inverse_transform(Yp_mean.reshape(-1, Yp_mean.shape[-1])).flatten()

    mae_validation = np.mean(MAE(Yp_mean, Y_test))#calcola la media del mae sul validation set e sul test set
    smape_validation = np.mean(RMSE(Yp_mean, Y_test))
    differenza=(abs(Yp_mean-Y_test)).flatten()#calcola gli errori in modulo sul test set
    print("errore max", max(differenza))#printa il massimo e il minimo dell'errore commesso
    print("errore min", min(differenza))
    print("  MAE: {:.3f} | RMSE: {:.3f} %".format(mae_validation, smape_validation))
    return_values = {'loss': mae_validation, 'MAE test': mae_validation,'RMSE test': smape_validation, 'hyper': hyperparameters,'status': STATUS_OK}#i risultati del processo vengono ritornati tramite un dizionario
    if trials.losses()[0] is not None:#la condizione controlla che nell'oggetto trials ci siano effettivamente delle losses. Trials.losses() riporta la lista di loss salvate nel processo di ottimizzazione
        MAEVal = trials.best_trial['result']['MAE test']#riporta il miglior valore del MAE durante il processo di ottimizzazione.
        sMAPEVal = trials.best_trial['result']['RMSE test']#riporta il miglior valore del RMSE durante il processo di ottimizzazione
        parametri = trials.best_trial['result']['hyper']#riporta la migliore scelta di iperparametri

        print('\n\nTested {}/{} iterations.'.format(len(trials.losses()) - 1,max_evals))
        print('Best MAE - Validation Dataset')
        print("  MAE: {:.3f} | RMSE: {:.3f} %".format(MAEVal, sMAPEVal))
    return return_values

def hyperparameter_optimizer(path_hyperparameters_folder=os.path.join('.', 'experimental_files'),
                             new_hyperopt=1, max_evals=1500):

    if not os.path.exists(path_hyperparameters_folder):
        os.makedirs(path_hyperparameters_folder)
    trials_file_name = 'DNN_hyperparameters'
    trials_file_path = os.path.join(path_hyperparameters_folder, trials_file_name)
    if new_hyperopt:#Se new_hyperopt è True inizializza un nuovo oggetto trials
        trials = Trials()
    else:
        trials = pc.load(open(trials_file_path, "rb"))
    space = _build_space()

    fmin_objective = partial(_hyperopt_objective, trials=trials, trials_file_path=trials_file_path,
                             max_evals=max_evals)
    fmin(fmin_objective, space=space, algo=tpe.suggest, max_evals=max_evals, trials=trials, verbose=False)#fmin da hyperopt performa l'ottimizzazione utilizzando l'algoritmo Tree-structured Parzen Estimators
import warnings
warnings.filterwarnings("ignore")
new_hyperopt = 1
max_evals = 25
path_hyperparameters_folder = "./experimental_files/"

if __name__ == "__main__":
  hyperparameter_optimizer(path_hyperparameters_folder=path_hyperparameters_folder,new_hyperopt=new_hyperopt, max_evals=max_evals)
  trials_file_name = 'DNN_hyperparameters'
  trials_file_path = os.path.join(path_hyperparameters_folder, trials_file_name)
  trials = pc.load(open(trials_file_path, "rb"))
  for trial in trials.trials:
      print(trial['result'])

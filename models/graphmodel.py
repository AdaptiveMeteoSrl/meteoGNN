# -*- coding: utf-8 -*-
"""GRAPHMODEL.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1317sRmCAotDxeJl-bZ7NrlNtZuPp8Zn4
"""

class Model(nn.Module):
    """Modello Graph Convolutional seguito da una serie di Linear"""
    def __init__(
        self,
        seq_len,
        pred_len,
        n_features,
        batch_size,
        hidden

    ):
        super(Model, self).__init__()
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.hidden = hidden
        self.n_features = n_features
        self.batch_size = batch_size
        self.num_nodes=5

        self.W1 = nn.Parameter(torch.rand((self.num_nodes, self.num_nodes, self.n_features, self.hidden), dtype=torch.float32))  #Una matrice di pesi per ogni interazione nodo-nodo
        self.bias=nn.Parameter(torch.rand((self.seq_len, self.num_nodes, self.hidden), dtype=torch.float32))                     #L'interazione avviene soltanto fra nodi allo stesso tempo

        self.nodes=nn.Linear(5,1)                                                                                                #Tre linear combinano le informazioni spaziali e temporali
        self.feat=nn.Linear(self.hidden,1)
        self.time=nn.Linear(self.seq_len,1)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.to(self.device)

    def forward(self, features, mask):
        A = mask
        features=features.reshape(self.batch_size,self.seq_len,self.num_nodes,self.n_features)
        prodotto1=torch.matmul(A,features)
        tutto = torch.einsum('ijkl,fklm->ijfm', prodotto1, self.W1)                           #Convoluzione
        conv1= torch.relu(tutto+self.bias)
        risultato = conv1
        risultato=self.feat(risultato)
        risultato=self.nodes(risultato.permute(0,1,3,2)).permute(0,1,3,2)
        risultato=self.time(risultato.permute(0,2,3,1)).permute(0,2,3,1)

        return risultato[:,-1,-1:,-1:]
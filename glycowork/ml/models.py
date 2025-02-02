import os
import torch
import numpy as np
try:
    from torch_geometric.nn import GraphConv
    from torch_geometric.nn import global_mean_pool as gap
except ImportError:
    raise ImportError('<torch_geometric missing; cannot do deep learning>')
import torch.nn.functional as F
from glycowork.glycan_data.loader import lib

device = "cpu"
if torch.cuda.is_available():
    device = "cuda:0"

this_dir, this_filename = os.path.split(__file__)  # Get path
trained_SweetNet = os.path.join(this_dir, 'glycowork_sweetnet_species.pt')
trained_LectinOracle = os.path.join(this_dir, 'glycowork_lectinoracle_600.pt')
trained_LectinOracle_flex = os.path.join(this_dir, 'glycowork_lectinoracle_600_flex.pt')
trained_NSequonPred = os.path.join(this_dir, 'NSequonPred_batch32.pt')

class SweetNet(torch.nn.Module):
    def __init__(self, lib_size, num_classes = 1):
        super(SweetNet, self).__init__()

        #convolution operations on the graph
        self.conv1 = GraphConv(128, 128)
        self.conv2 = GraphConv(128, 128)
        self.conv3 = GraphConv(128, 128)
        
        #node embedding
        self.item_embedding = torch.nn.Embedding(num_embeddings = lib_size+1,
                                                 embedding_dim = 128)
        #fully connected part
        self.lin1 = torch.nn.Linear(128, 1024)
        self.lin2 = torch.nn.Linear(1024, 128)
        self.lin3 = torch.nn.Linear(128, num_classes)
        self.bn1 = torch.nn.BatchNorm1d(1024)
        self.bn2 = torch.nn.BatchNorm1d(128)
        self.act1 = torch.nn.LeakyReLU()
        self.act2 = torch.nn.LeakyReLU()      
  
    def forward(self, x, edge_index, batch, inference = False):
        
        #getting node features
        x = self.item_embedding(x)
        x = x.squeeze(1)

        #graph convolution operations
        x = F.leaky_relu(self.conv1(x, edge_index))
        x = F.leaky_relu(self.conv2(x, edge_index))
        x = F.leaky_relu(self.conv3(x, edge_index))
        x = gap(x, batch)

        #fully connected part
        x = self.act1(self.bn1(self.lin1(x)))
        x_out = self.bn2(self.lin2(x))   
        x = F.dropout(self.act2(x_out), p = 0.5, training = self.training)

        x = self.lin3(x).squeeze(1)

        if inference:
          return x, x_out
        else:
          return x

class NSequonPred(torch.nn.Module):
    def __init__(self):
        super(NSequonPred, self).__init__() 

        self.fc1 = torch.nn.Linear(1280, 512)
        self.fc2 = torch.nn.Linear(512, 256)
        self.fc3 = torch.nn.Linear(256, 64)
        self.fc4 = torch.nn.Linear(64, 1)

        self.bn1 = torch.nn.BatchNorm1d(512)
        self.bn2 = torch.nn.BatchNorm1d(256)
        self.bn3 = torch.nn.BatchNorm1d(64)

    def forward(self, x):
      x = F.dropout(F.rrelu(self.bn1(self.fc1(x))), p = 0.2, training = self.training)
      x = F.dropout(F.rrelu(self.bn2(self.fc2(x))), p = 0.2, training = self.training)
      x = F.dropout(F.rrelu(self.bn3(self.fc3(x))), p = 0.1, training = self.training)
      x = self.fc4(x)
      return x

def sigmoid_range(x, low, high):
    "Sigmoid function with range `(low, high)`"
    return torch.sigmoid(x) * (high - low) + low

class SigmoidRange(torch.nn.Module):
    "Sigmoid module with range `(low, x_max)`"
    def __init__(self, low, high):
      super(SigmoidRange, self).__init__()
      self.low, self.high = low,high
    def forward(self, x): return sigmoid_range(x, self.low, self.high)

class LectinOracle(torch.nn.Module):
  def __init__(self, input_size_glyco, hidden_size = 128, num_classes = 1, data_min = -11.355,
               data_max = 23.892, input_size_prot = 1280):
    super(LectinOracle,self).__init__()
    self.input_size_prot = input_size_prot
    self.input_size_glyco = input_size_glyco
    self.hidden_size = hidden_size
    self.num_classes = num_classes
    self.data_min = data_min
    self.data_max = data_max

    #graph convolution operations for the glycan
    self.conv1 = GraphConv(self.hidden_size, self.hidden_size)
    self.conv2 = GraphConv(self.hidden_size, self.hidden_size)
    self.conv3 = GraphConv(self.hidden_size, self.hidden_size)
    #node embedding for the glycan
    self.item_embedding = torch.nn.Embedding(num_embeddings = self.input_size_glyco+1,
                                             embedding_dim = self.hidden_size)
    
    #fully connected part for the protein
    self.prot_encoder1 = torch.nn.Linear(self.input_size_prot, 400)
    self.prot_encoder2 = torch.nn.Linear(400, 128)
    self.bn_prot1 = torch.nn.BatchNorm1d(400)
    self.bn_prot2 = torch.nn.BatchNorm1d(128)
    self.dp_prot1 = torch.nn.Dropout(0.2)
    self.dp_prot2 = torch.nn.Dropout(0.1)
    self.act_prot1 = torch.nn.LeakyReLU()
    self.act_prot2 = torch.nn.LeakyReLU()
    
    #combined fully connected part
    self.fc1 = torch.nn.Linear(128+self.hidden_size, int(np.round(self.hidden_size/2)))
    self.fc2 = torch.nn.Linear(int(np.round(self.hidden_size/2)), self.num_classes)
    self.bn1 = torch.nn.BatchNorm1d(int(np.round(self.hidden_size/2)))
    self.dp1 = torch.nn.Dropout(0.5)    
    self.act1 = torch.nn.LeakyReLU()    
    self.sigmoid = SigmoidRange(self.data_min, self.data_max)
    
    
  def forward(self, prot, nodes, edge_index, batch, inference = False):
    #fully connected part for the protein
    embedded_prot = self.bn_prot1(self.act_prot1(self.dp_prot1(self.prot_encoder1(prot))))
    embedded_prot = self.bn_prot2(self.act_prot2(self.dp_prot2(self.prot_encoder2(embedded_prot))))

    #getting glycan node features
    x = self.item_embedding(nodes)
    x = x.squeeze(1) 

    #glycan graph convolution operations
    x = F.leaky_relu(self.conv1(x, edge_index))
    x = F.leaky_relu(self.conv2(x, edge_index))
    x = F.leaky_relu(self.conv3(x, edge_index))
    x = gap(x, batch)
    
    #combining results from protein and glycan
    h_n = torch.cat((embedded_prot, x), 1)
    
    #fully connected part
    h_n = self.act1(self.bn1(self.fc1(h_n)))

    #1
    x1 = self.fc2(self.dp1(h_n))
    #2
    x2 = self.fc2(self.dp1(h_n))
    #3
    x3 = self.fc2(self.dp1(h_n))
    #4
    x4 = self.fc2(self.dp1(h_n))
    #5
    x5 = self.fc2(self.dp1(h_n))
    #6
    x6 = self.fc2(self.dp1(h_n))
    #7
    x7 = self.fc2(self.dp1(h_n))
    #8
    x8 = self.fc2(self.dp1(h_n))
    
    out =  self.sigmoid(torch.mean(torch.stack([x1, x2, x3, x4, x5, x6, x7, x8]), dim = 0))
    
    if inference:
      return out, embedded_prot, x
    else:
      return out

class LectinOracle_flex(torch.nn.Module):
  def __init__(self, input_size_glyco, hidden_size = 128, num_classes = 1, data_min = -11.355,
               data_max = 23.892, input_size_prot = 1000):
    super(LectinOracle_flex,self).__init__()
    self.input_size_prot = input_size_prot
    self.input_size_glyco = input_size_glyco
    self.hidden_size = hidden_size
    self.num_classes = num_classes
    self.data_min = data_min
    self.data_max = data_max

    #graph convolution operations for the glycan
    self.conv1 = GraphConv(self.hidden_size, self.hidden_size)
    self.conv2 = GraphConv(self.hidden_size, self.hidden_size)
    self.conv3 = GraphConv(self.hidden_size, self.hidden_size)
    #node embedding for the glycan
    self.item_embedding = torch.nn.Embedding(num_embeddings = self.input_size_glyco+1,
                                             embedding_dim = self.hidden_size)
    
    #ESM-1b mimicking
    self.fc1 = torch.nn.Linear(self.input_size_prot, 4000)
    self.fc2 = torch.nn.Linear(4000, 2000)
    self.fc3 = torch.nn.Linear(2000, 1280)
    self.dp1 = torch.nn.Dropout(0.3)
    self.dp2 = torch.nn.Dropout(0.2)
    self.act1 = torch.nn.LeakyReLU()
    self.act2 = torch.nn.LeakyReLU()
    self.bn1 = torch.nn.BatchNorm1d(4000)
    self.bn2 = torch.nn.BatchNorm1d(2000)
    
    #fully connected part for the protein
    self.prot_encoder1 = torch.nn.Linear(1280, 400)
    self.prot_encoder2 = torch.nn.Linear(400, 128)
    self.dp_prot1 = torch.nn.Dropout(0.2)
    self.dp_prot2 = torch.nn.Dropout(0.1)
    self.bn_prot1 = torch.nn.BatchNorm1d(400)
    self.bn_prot2 = torch.nn.BatchNorm1d(128)
    self.act_prot1 = torch.nn.LeakyReLU()
    self.act_prot2 = torch.nn.LeakyReLU()

    #combined fully connected part
    self.dp1_n = torch.nn.Dropout(0.5) 
    self.fc1_n = torch.nn.Linear(128+self.hidden_size, int(np.round(self.hidden_size/2)))
    self.fc2_n = torch.nn.Linear(int(np.round(self.hidden_size/2)), self.num_classes)
    self.bn1_n = torch.nn.BatchNorm1d(int(np.round(self.hidden_size/2)))
    self.act1_n = torch.nn.LeakyReLU()
    self.sigmoid = SigmoidRange(self.data_min, self.data_max)
    
    
  def forward(self, prot, nodes, edge_index, batch, inference = False):
    #ESM-1b mimicking
    prot = self.dp1(self.act1(self.bn1(self.fc1(prot))))
    prot = self.dp2(self.act2(self.bn2(self.fc2(prot))))
    prot = self.fc3(prot)
    #fully connected part for the protein
    embedded_prot = self.dp_prot1(self.act_prot1(self.bn_prot1(self.prot_encoder1(prot))))
    embedded_prot = self.dp_prot2(self.act_prot2(self.bn_prot2(self.prot_encoder2(embedded_prot))))

    #getting glycan node features
    x = self.item_embedding(nodes)
    x = x.squeeze(1) 

    #glycan graph convolution operations
    x = F.leaky_relu(self.conv1(x, edge_index))
    x = F.leaky_relu(self.conv2(x, edge_index))
    x = F.leaky_relu(self.conv3(x, edge_index))
    x = gap(x, batch)

    #combining results from protein and glycan
    h_n = torch.cat((embedded_prot, x), 1)

    #fully connected part    
    h_n = self.act1_n(self.bn1_n(self.fc1_n(h_n)))

    #1
    x1 = self.fc2_n(self.dp1_n(h_n))
    #2
    x2 = self.fc2_n(self.dp1_n(h_n))
    #3
    x3 = self.fc2_n(self.dp1_n(h_n))
    #4
    x4 = self.fc2_n(self.dp1_n(h_n))
    #5
    x5 = self.fc2_n(self.dp1_n(h_n))
    #6
    x6 = self.fc2_n(self.dp1_n(h_n))
    #7
    x7 = self.fc2_n(self.dp1_n(h_n))
    #8
    x8 = self.fc2_n(self.dp1_n(h_n))
    
    out =  self.sigmoid(torch.mean(torch.stack([x1, x2, x3, x4, x5, x6, x7, x8]), dim = 0))
    
    if inference:
      return out, embedded_prot, x
    else:
      return out

def init_weights(model, mode = 'sparse', sparsity = 0.1):
    """initializes linear layers of PyTorch model with a weight initialization\n
    | Arguments:
    | :-
    | model (Pytorch object): neural network (such as SweetNet) for analyzing glycans
    | mode (string): which initialization algorithm; choices are 'sparse','kaiming','xavier';default:'sparse'
    | sparsity (float): proportion of sparsity after initialization; default:0.1 / 10%
    """
    if type(model) == torch.nn.Linear:
        if mode == 'sparse':
            torch.nn.init.sparse_(model.weight, sparsity = sparsity)
        elif mode == 'kaiming':
            torch.nn.init.kaiming_uniform_(model.weight)
        elif mode == 'xavier':
            torch.nn.init.xavier_uniform_(model.weight)
        else:
            print("This initialization option is not supported.")

def prep_model(model_type, num_classes, libr = None,
               trained = False):
    """wrapper to instantiate model, initialize it, and put it on the GPU\n
    | Arguments:
    | :-
    | model_type (string): string indicating the type of model
    | num_classes (int): number of unique classes for classification
    | libr (list): sorted list of unique glycoletters observed in the glycans of our dataset\n
    | Returns:
    | :-
    | Returns PyTorch model object
    """
    if libr is None:
        libr = lib
    if model_type == 'SweetNet':
        model = SweetNet(len(libr), num_classes = num_classes)
        model = model.apply(lambda module: init_weights(module, mode = 'sparse'))
        if trained:
            model.load_state_dict(torch.load(trained_SweetNet))
        model = model.to(device)
    elif model_type == 'LectinOracle':
        model = LectinOracle(len(libr), num_classes = num_classes)
        model = model.apply(lambda module: init_weights(module, mode = 'xavier'))
        if trained:
            model.load_state_dict(torch.load(trained_LectinOracle))
        model = model.to(device)
    elif model_type == 'LectinOracle_flex':
        model = LectinOracle_flex(len(libr), num_classes = num_classes)
        model = model.apply(lambda module: init_weights(module, mode = 'xavier'))
        if trained:
            model.load_state_dict(torch.load(trained_LectinOracle_flex))
        model = model.to(device)
    elif model_type == 'NSequonPred':
        model = NSequonPred()
        model = model.apply(lambda module: init_weights(module, mode = 'xavier'))
        if trained:
            model.load_state_dict(torch.load(trained_NSequonPred))
        model = model.to(device)
    else:
        print("Invalid Model Type")
    return model

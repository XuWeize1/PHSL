# import dgl
import torch
import torch.nn as nn

from layers import HGNNConv_dense
from utils import *
import math

class Stage_GNN_learner(nn.Module):
    def __init__(self, nlayers, isize, osize, k, knn_metric, sparse, act, internal_type, ks, share_up_gnn, fusion_ratio, stage_fusion_ratio, 
                 epsilon, add_vertical_position, v_pos_dim, dropout_v_pos, up_gnn_nlayers, dropout_up_gnn, add_embedding):
        super(Stage_GNN_learner, self).__init__()

        self.internal_layers = nn.ModuleList()
        print('Stage Internal type =', internal_type)
        self.internal_type = internal_type
        if self.internal_type == 'gnn':
            if nlayers == 1:
                self.internal_layers.append(HGNNConv_dense(isize, 32,osize))
            else:
                self.internal_layers.append(HGNNConv_dense(isize, 32,osize))
                for _ in range(nlayers - 2):
                    self.internal_layers.append(HGNNConv_dense(osize,32, osize))
                self.internal_layers.append(HGNNConv_dense(osize,32, osize))
        elif self.internal_type == 'mlp':
            if nlayers == 1:
                self.internal_layers.append(nn.Linear(isize, osize))
            else:
                self.internal_layers.append(nn.Linear(isize, osize))
                for _ in range(nlayers - 2):
                    self.internal_layers.append(nn.Linear(osize, osize))
                self.internal_layers.append(nn.Linear(osize, osize))

        self.k = k
        self.sparse = sparse
        self.act = act
        self.epsilon = epsilon
        self.fusion_ratio = fusion_ratio
        self.add_embedding = add_embedding
        ## stage module
        self.ks = ks
        self.l_n = len(self.ks)
        print("ks",self.ks)
        print("ln",self.l_n)

        # self.vertical_position_map = nn.Linear(5*int(math.log(n_nums,2)), 16)
        # self.vertical_position_map2 = nn.Linear(16, 16)

        if self.l_n > 0:
            self.stage_fusion_ratio = stage_fusion_ratio
            # down score
            self.score_layer = HGNNConv_dense(osize,32, 1)


            ## up_gnn
            self.share_up_gnn = share_up_gnn
            self.up_gnn_nlayers = up_gnn_nlayers
            if self.up_gnn_nlayers > 1:
                self.dropout_up_gnn = dropout_up_gnn
            
            self.up_gnn_layers = nn.ModuleList()
            if self.share_up_gnn:
                # print("a")
                self.up_gnn_layers.append(HGNNConv_dense(osize, 256,  osize))
                if self.up_gnn_nlayers == 2:
                    self.up_gnn_layers.append(HGNNConv_dense(osize, 256 , osize))
            else:
                # print("b")
                for i in range(self.l_n):
                    self.up_gnn_layers_second = nn.ModuleList()
                    self.up_gnn_layers_second.append(HGNNConv_dense(osize, 64,  osize))
                    if self.up_gnn_nlayers == 2:
                        self.up_gnn_layers_second.append(HGNNConv_dense(osize, 64, osize))
                    self.up_gnn_layers.append(self.up_gnn_layers_second)


            # # cross layer mi
            # self.add_cross_mi = add_cross_mi
            # if self.add_cross_mi:

            #     self.discriminator = nn.Bilinear(osize, osize, 1)
            #     self.cross_layer_mi_loss = nn.BCEWithLogitsLoss()

            #     self.cross_mi_layers = nn.ModuleList()
            #     if cross_mi_nlayer == 1:
            #         self.cross_mi_layers.append(HGNNConv_dense(osize, osize))
            #     else:
            #         self.cross_mi_layers.append(HGNNConv_dense(osize, osize))
            #         for _ in range(cross_mi_nlayer - 2):
            #             self.cross_mi_layers.append(
            #                 HGNNConv_dense(osize, osize))
            #         self.cross_mi_layers.append(HGNNConv_dense(osize, osize))


            # vectival position
            self.add_vertical_position = add_vertical_position
            if self.add_vertical_position:
                self.dropout_v_pos = dropout_v_pos
                self.v_pos_dim = v_pos_dim
                self.vertival_pos_embedding = nn.Embedding(
                    self.l_n+1, self.v_pos_dim)
                self.map_v_pos_linear1 = nn.Linear(osize+self.v_pos_dim, osize)
                self.map_v_pos_linear2 = nn.Linear(osize, osize)

            # self.position_regularization = position_regularization


    def up_gnn_forward(self, h, adj, deep=None):
        if self.share_up_gnn:
            for i, up_layer in enumerate(self.up_gnn_layers):
                h = up_layer(h, adj)
                if i != (len(self.up_gnn_layers) - 1):
                    h = F.relu(h)
                    if self.dropout_up_gnn>0:
                        h = F.dropout(h, self.dropout_up_gnn, training=self.training)
            return h
        else:
            up_gnn_layers = self.up_gnn_layers[deep]
            for i, up_layer in enumerate(up_gnn_layers):
                h = up_layer(h, adj)
                if i != (len(up_gnn_layers) - 1):
                    h = F.relu(h)
                    if self.dropout_up_gnn>0:
                        h = F.dropout(h, self.dropout_up_gnn, training=self.training)
            return h



    def internal_forward(self, h, adj):
        if self.internal_type == 'gnn':
            for i, layer in enumerate(self.internal_layers):
                h = layer(h, adj)
                if i != (len(self.internal_layers) - 1):
                    if self.act == "relu":
                        h = F.relu(h)
                    elif self.act == "tanh":
                        h = F.tanh(h)
            return h
        elif self.internal_type == 'mlp':
            for i, layer in enumerate(self.internal_layers):
                h = layer(h)
                if i != (len(self.internal_layers) - 1):
                    if self.act == "relu":
                        h = F.relu(h)
                    elif self.act == "tanh":
                        h = F.tanh(h)
            return h
    
    
    # def cross_mi_forward(self, h, adj):
    #     assert (self.l_n>0 and self.add_cross_mi)

    #     for i, layer in enumerate(self.cross_mi_layers):
    #         h = layer(h, adj)
    #         if i != (len(self.cross_mi_layers) - 1):
    #             if self.act == "relu":
    #                 h = F.relu(h)
    #             elif self.act == "tanh":
    #                 h = F.tanh(h)
    #     return h


    def forward(self, features, adj):
        # v_embeddings = self.vertical_position_map(pos_infos)
        # print("feature",features.shape)
        # print("adj",adj.shape)


        embeddings = self.internal_forward(features, adj)
        # print("embed",embeddings.shape)

        cur_embeddings = embeddings

        adj_ = adj
        embeddings_ = embeddings

        # all_stage_adjs = []

        # cross_layer_mi_val = None
        # position_reg_loss = torch.tensor(0.0).to(features.device)

        if self.l_n > 0:
            # adj_ms = []
            indices_list = []
            down_outs = []

            n_node = features.shape[0]
            pre_idx = torch.range(0, n_node-1).long()
            for i in range(self.l_n): # [0,1,2]
                # adj_ms.append(adj_)
                down_outs.append(embeddings_)

                if i == 0:
                    y = F.relu(self.score_layer(embeddings_, adj_).squeeze())

                else:
                    y = F.relu(self.score_layer(embeddings_[pre_idx,:], normalize(adj_, 'row', self.sparse)).squeeze())
            
                score, idx = torch.topk(y, max(2, int(self.ks[i]*adj_.shape[0])))

                _, indices = torch.sort(idx)
                new_score = score[indices]
                new_idx = idx[indices].to(pre_idx.device)
                
                # global node index
                pre_idx = pre_idx[new_idx]
                pre_idx = pre_idx.cuda()
                indices_list.append(pre_idx)
                adj_ = adj[pre_idx, :]
                non_zero_columns = torch.any(adj_ != 0, dim=0)
                adj_ = adj_[:, non_zero_columns]
                new_features = features[pre_idx, :]
                mask_score = torch.zeros(n_node).to(features.device)
                # mask_score[pre_idx] = new_score
                mask_score[pre_idx] = new_score.to(torch.float)
                embeddings_ = torch.mul(embeddings_, torch.unsqueeze(mask_score, -1) + torch.unsqueeze(1-mask_score, -1).detach())

            if self.add_vertical_position:
                vertical_position = torch.zeros(n_node).long().to(adj.device)
                for i in range(self.l_n):
                    vertical_position[indices_list[i]] = int(i+1)


                node_v_pos_embeddings = self.vertival_pos_embedding(vertical_position)

                embeddings_ = torch.cat((embeddings_, node_v_pos_embeddings), dim=-1)
                embeddings_ = F.sigmoid(self.map_v_pos_linear1(embeddings_.float()))
                embeddings_ = F.dropout(embeddings_, self.dropout_v_pos, training=self.training)
                embeddings_ = self.map_v_pos_linear2(embeddings_)


        if self.add_embedding:
            embeddings_ += cur_embeddings
        embeddings = F.normalize(embeddings_, dim=1, p=2)
        learned_adj = cal_similarity_graph(embeddings)
        if self.k:
            learned_adj = top_k(learned_adj, self.k + 1)
        mask = (learned_adj > self.epsilon).float()
        mask.requires_grad = False
        learned_adj = learned_adj * mask
        # print('adj',adj_.shape)

        if self.l_n > 0:
            for j in reversed(range(self.l_n)):
                learned_adj = symmetrize(learned_adj)
                # if self.discrete_graph:
                #     learned_adj = self.to_discrete_graph(learned_adj)
                learned_adj = normalize(learned_adj, 'sym', self.sparse)
                adj = self.only_modify_subgraph(learned_adj, adj, indices_list[j], self.stage_fusion_ratio)

                # if self.modify_subgraph:
                #     adj = self.only_modify_subgraph(learned_adj, adj, indices_list[j], self.stage_fusion_ratio)
                # else:
                #     # only preserve the subgraph gradient
                #     learned_adj = self.mask_subgraph(indices_list[j], learned_adj)
                #     # fuse the origin graph and learn graph
                #     adj = self.fusion_ratio * learned_adj + (1-self.fusion_ratio) * adj

                # store learned graph adj
                # all_stage_adjs.append(adj)

                # updata pre_layer subgraph based cur learned subgraph
                embeddings = down_outs[j]
                if self.add_vertical_position:
                    embeddings = torch.cat((embeddings, node_v_pos_embeddings), dim=-1)
                    embeddings = F.sigmoid(self.map_v_pos_linear1(embeddings.float()))
                    embeddings = F.dropout(embeddings, self.dropout_v_pos, training=self.training)
                    embeddings = self.map_v_pos_linear2(embeddings)


                embeddings = self.up_gnn_forward(embeddings, normalize(adj, 'sym', self.sparse), deep=j)

                if self.add_embedding:
                    embeddings += cur_embeddings
                embeddings = F.normalize(embeddings, dim=1, p=2)
                learned_adj = cal_similarity_graph(embeddings)
                if self.k:
                    learned_adj = top_k(learned_adj, self.k + 1)

                # filter the elements below epsilon
                mask = (learned_adj > self.epsilon).float()
                mask.requires_grad = False
                learned_adj = learned_adj * mask

        learned_adj = symmetrize(learned_adj)
        learned_adj = normalize(learned_adj, 'sym', self.sparse)

        # fuse the origin graph and learn graph, and store
        prediction_adj = self.fusion_ratio * learned_adj + (1-self.fusion_ratio) * adj
        # prediction_adj = normalize(prediction_adj, 'sym', self.sparse)
        threshold = 0.002
        device = prediction_adj.device
        dtype = prediction_adj.dtype
        # 将小于阈值的元素置为0
        prediction_adj = torch.where(
            prediction_adj < threshold,
            torch.tensor(0.0, device=device, dtype=dtype),
            prediction_adj
        )


        return learned_adj, prediction_adj, adj_, new_features
        # return adj_, new_features, train_mask, test_mask, val_mask

    # def anchor_position_regularization(self, anchor_postions, socres):
    #     node_num = anchor_postions.shape[0]
    #     mask = torch.eye(node_num).to(anchor_postions.device)
    #     pos_scores = torch.mul(anchor_postions, torch.unsqueeze(socres, -1))
    #     scores_norm = pos_scores.div(torch.norm(pos_scores, p=2, dim=-1, keepdim=True)+1e-12)
    #     pos_loss = torch.mm(scores_norm, scores_norm.transpose(-1, -2)) * (1-mask)
    #     return torch.sum(pos_loss) / node_num


    def stage_recover_adj(self, cur_small_g, pre_big_g, idx):
            n_nums = idx.shape[0]
            # x_index = idx.unsqueeze(1).repeat(1,n_nums).flatten()
            # y_index = idx.repeat(1,n_nums).flatten()
            x_index = idx.repeat(n_nums)
            y_index = idx.repeat_interleave(n_nums)
            cur_adj_v = cur_small_g.flatten()
            new_pre_adj = pre_big_g.index_put([x_index,y_index],cur_adj_v)
            return new_pre_adj


    def only_modify_subgraph(self, cur_g, pre_g, idx, fusion_ratio):
        cur_small_g = cur_g[idx,:][:,idx]
        pre_small_g = pre_g[idx,:][:,idx]
        new_small_g = cur_small_g * fusion_ratio + pre_small_g * (1-fusion_ratio)

        new_g = self.stage_recover_adj(new_small_g, pre_g, idx)
        return new_g


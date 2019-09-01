import numpy as np
import matplotlib.pyplot as plt
#from EnsemblePursuitPyTorch_threshold import EnsemblePursuitPyTorch
import sys
sys.path.append("..")
from EnsemblePursuitModule.EnsemblePursuitPyTorch import EnsemblePursuitPyTorch
from EnsemblePursuitModule.EnsemblePursuitNumpy import EnsemblePursuitNumpy
#from EnsemblePursuitNumpy import EnsemblePursuitNumpy
from scipy import io
import time
import os
import matplotlib
import scipy.io as sio


class SpontaneousBehaviorPipeline():
    def __init__(self,data_path, mouse_filename,model,nr_of_components,lambd_=None,save=False,save_path=None):
        self.data_path=data_path
        self.model=model
        self.lambd_=lambd_
        self.nr_of_components=nr_of_components
        self.mouse_filename=mouse_filename
        self.save=save
        self.save_path=save_path

    def bin_data(self,X,motionSVD,parea,tbin=3.0):
        NT = motionSVD.shape[1]
        self.nt = int(np.floor(NT/tbin))
        motionSVD -= motionSVD.mean(axis=1)[:,np.newaxis]
        parea  -= np.nanmean(parea)
        parea[np.isnan(parea)] = 0
        tbin = int(tbin)

        beh = np.reshape(motionSVD[:,:self.nt*tbin], (motionSVD.shape[0], self.nt, tbin)).mean(axis=-1)
        pup = np.reshape(parea[:nt*tbin], (self.nt, tbin)).mean(axis=-1)
        # using this format bin S
        X = np.reshape(X[:,:self.nt*tbin], (X.shape[0],self.nt, tbin)).mean(axis=-1)
        return X,beh,pup

    def fit_model(self,bin=False):
        mt = sio.loadmat(self.data_path+self.mouse_filename) # neurons by timepoints
        self.X = mt['Fsp']
        self.motionSVD=np.array(mt['beh'][0]['face'][0]['motionSVD'][0][0]).T
        self.parea =np.array(mt['beh'][0]['pupil'][0]['area'][0][0])
        if bin==True:
            self.X,self.motionSVD,self.parea=bin_data(self.X,self.motionSVD,self.parea)
        else:
            self.nt= self.motionSVD.shape[1]
            tbin=1
            self.motionSVD = np.reshape(self.motionSVD[:,:self.nt*tbin], (self.motionSVD.shape[0], self.nt, tbin)).mean(axis=-1)
            self.parea= np.reshape(self.parea[:self.nt*tbin], (self.nt, tbin)).mean(axis=-1)

        if self.model=='EnsemblePursuit_numpy':
            options_dict={'seed_neuron_av_nr':100,'min_assembly_size':8}
            ep_np=EnsemblePursuitNumpy(n_ensembles=self.nr_of_components,lambd=0.01,options_dict=options_dict)
            U,V=ep_np.fit_transform(self.X)
            if self.save==True:
                bundle={'U':U,'V':V}
                np.save(self.save_path+self.mouse_filename+'_spont_ep_numpy.npy',bundle)
            return U,V

    def split_test_train(self):
        # split into train-test
        # * use interleaved segments *
        nsegs = 20
        nlen  = self.nt/nsegs
        ninds = np.linspace(0,self.nt-nlen,nsegs).astype(int)
        itest = (ninds[:,np.newaxis] + np.arange(0,nlen*0.25,1,int)).flatten()
        itrain = np.ones(self.nt, np.bool)
        itrain[itest] = 0

        plt.plot(itrain)
        plt.show()

        return itrain, itest

    def predict_neural_activity_using_pupil(self,V):
        itrain, itest=self.split_test_train()
        #### PREDICT USING PUPIL WITH LINEAR REGRESSION
        #pup =np.array(mt['beh'][0]['pupil'][0]['area'][0][0])
        A = np.matmul(self.parea[itrain], V[:,itrain].T)/(self.parea**2).sum()

        Vpredp = np.matmul(A[:,np.newaxis], self.parea[itest][np.newaxis,:])

        varexp_pupil = 1 - ((Vpredp - V[:,itest])**2).sum(axis=1)/(V[:,itest]**2).sum(axis=1)

        return Vpredp,varexp_pupil

    def predict_neural_activity_using_behavior(self,V):
        itrain, itest=self.split_test_train()
        print(V.shape)
        print(self.motionSVD.shape)
        #### PREDICT USING BEHAVIOR PC'S
        ## regularized linear regression from behavior to neural PCs
        covM = np.matmul(self.motionSVD[:,itrain], self.motionSVD[:,itrain].T)
        lam = 1e5 # regularizer
        covM += lam*np.eye(self.motionSVD.shape[0])
        A = np.linalg.solve(covM, np.matmul(self.motionSVD[:,itrain], V[:,itrain].T))

        Vpred = np.matmul(A.T, self.motionSVD[:,itest])

        varexp = 1 - ((Vpred - V[:,itest])**2).sum(axis=1)/(V[:,itest]**2).sum(axis=1)
        return Vpred,varexp

    def plot_var_exp(self,V,component_index=1):
        if self.model=='EnsemblePursuit_numpy':
            V=V.T
        itrain, itest=self.split_test_train()
        Vpred,varexp=self.predict_neural_activity_using_behavior(V)
        Vpredp,varexp_pupil=self.predict_neural_activity_using_pupil(V)
        fig=plt.figure(figsize=(12,3))
        ipc = 1 ### which PC to plot

        ax = fig.add_axes([0.05,.05,.75,.95])
        ax.plot(V[ipc,itest], label='neural PC')
        ax.plot(Vpred[ipc], color='k', label='face PC prediction')
        ax.set_title('PC %d'%ipc)
        ax.set_xlabel('time')
        ax.set_ylabel('activity')
        ax.legend()

        ax = fig.add_axes([0.9,.05, .2, .8])
        ax.semilogx(np.arange(1,varexp.size+1), varexp, color='k')
        ax.scatter(ipc+1, varexp[ipc],marker='x',color='r',s=200, lw=4, zorder=10)
        ax.semilogx(np.arange(1,varexp.size+1), varexp_pupil, color=[0.,.5,0])
        ax.text(1,0,'pupil',color=[0,.5,0])
        ax.text(10,0.2,'motion SVD')
        ax.set_xlabel('PC')
        ax.set_ylabel('fraction variance explained')
        ax.set_title('PC %d, varexp=%0.2f'%(ipc,varexp[ipc]))
        plt.show()
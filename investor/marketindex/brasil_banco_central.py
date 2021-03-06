import pandas as pd

from .. import MarketIndex

class BCBMarketIndex(MarketIndex):
    # Tabela (dita obsoleta) com o código dos índices:
    # https://www.bcb.gov.br/estatisticas/indecoreestruturacao

    series={
        'CDI': dict(
            url="https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json",
            home=''
        ),
        'IPCA': dict(
            # IPCA Serviços. Outros IPCAs: https://dadosabertos.bcb.gov.br/dataset?q=ipca
            url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json",
            home = 'https://dadosabertos.bcb.gov.br/dataset/10844-indice-de-precos-ao-consumidor-amplo-ipca---servicos'
        ),
        'SELIC': dict(
            url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json",
            home = 'https://dadosabertos.bcb.gov.br/dataset/11-taxa-de-juros---selic'
        ),
        'IGPM': dict(
            # url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4175/dados?formato=json",
            url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.189/dados?formato=json",
            home = 'https://dadosabertos.bcb.gov.br/dataset/4175-divida-mobiliaria---participacao-por-indexador---posicao-em-carteira---igp-m'
        ),
        'INPC': dict(
            url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.188/dados?formato=json",
            home = ''
        ),
    }



    def __init__(self, name, isRate=True, cache=None, refresh=False):
        if name in self.series:
            s=self.series[name]
        else:
            raise Exception(f'BCBMarketIndex: market index not found: {name}')

        super().__init__(kind='BCBMarketIndex', id=name, currency='BRL', isRate=isRate, cache=cache, refresh=refresh)



    def refreshData(self):
        self.data=pd.read_json(self.series[self.id]['url'])



    def processData(self):
        self.data['time']=pd.to_datetime(self.data.data,dayfirst=True)
        self.data['rate']=self.data.valor/100
        self.data.drop(['data', 'valor'], axis=1, inplace=True)
        self.data.set_index('time', inplace=True)
        self.data.sort_index(inplace=True)

        self.data['value']=0.0
        start=1
        for i in range(self.data.shape[0]):
            if i==0:
                self.data.iat[i,1]=start*(1+self.data.iat[i,0])
            else:
                self.data.iat[i,1]=self.data.iat[i-1,1]*(1+self.data.iat[i,0])

        self.data=self.data[['value','rate']]

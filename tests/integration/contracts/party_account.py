# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Owner-controlled real IC payer used to verify immediate-caller authorization."""
from genlayer import *

class PartyAccount(gl.Contract):
    owner: Address
    book: Address

    def __init__(self,owner:str):
        self.owner=Address(owner)
        self.book=Address('0x'+'00'*20)

    def _owner(self):
        if gl.message.sender_address!=self.owner:raise gl.vm.UserError('[EXPECTED] Only party owner')

    @gl.public.write
    def configure(self,book:str)->None:
        self._owner()
        if self.book!=Address('0x'+'00'*20):raise gl.vm.UserError('[EXPECTED] Already configured')
        self.book=Address(book)

    @gl.public.write
    def create(self,reference:str,payee:str,url:str,digest:str,principal:int)->None:
        self._owner()
        gl.get_contract_at(self.book).emit(on='finalized').create_escrow(reference,payee,url,digest,principal,86400,86400,1000,3600,86400,5000)

    @gl.public.write
    def accept_delivery(self,escrow_id:str)->None:
        self._owner()
        gl.get_contract_at(self.book).emit(on='finalized').accept_delivery(escrow_id)

    @gl.public.write
    def withdraw(self,amount:int,recipient:str,reference:str)->None:
        self._owner()
        gl.get_contract_at(self.book).emit(on='finalized').withdraw(amount,recipient,'account',reference)
